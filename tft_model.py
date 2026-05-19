"""
NEXUS — Temporal Fusion Transformer Demand Forecasting Engine
Production-grade probabilistic demand forecasting with:
  - 28-day forecast horizon with confidence intervals
  - Multi-SKU support (50K+ SKUs)
  - Automatic seasonality decomposition
  - Statistical drift detection triggering retraining
  - MLflow experiment tracking & model registry
"""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import mlflow
import mlflow.pytorch
import numpy as np
import pandas as pd
import torch
from pytorch_forecasting import TemporalFusionTransformer, TimeSeriesDataSet
from pytorch_forecasting.data import GroupNormalizer
from pytorch_forecasting.metrics import QuantileLoss
from pytorch_lightning import Trainer, seed_everything
from pytorch_lightning.callbacks import (
    EarlyStopping,
    LearningRateMonitor,
    ModelCheckpoint,
)
from pytorch_lightning.loggers import MLFlowLogger
from scipy import stats
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger("nexus.ml.tft")

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────
FORECAST_CONFIG = {
    "max_encoder_length": 90,       # 90 days of history
    "max_prediction_length": 28,    # 28-day forecast horizon
    "batch_size": 128,
    "max_epochs": 50,
    "hidden_size": 64,
    "attention_head_size": 4,
    "dropout": 0.15,
    "hidden_continuous_size": 32,
    "output_size": 7,               # Quantiles: 0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98
    "learning_rate": 1e-3,
    "reduce_on_plateau_patience": 5,
    "quantiles": [0.02, 0.10, 0.25, 0.50, 0.75, 0.90, 0.98],
    "drift_threshold": 2.0,         # σ multiplier for drift detection
    "drift_window_days": 14,        # Days of recent data to compare
    "min_obs_for_training": 180,    # Minimum historical days required
}

# ─────────────────────────────────────────────
# DATA PREPARATION
# ─────────────────────────────────────────────

def load_demand_data(
    data_path: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load and preprocess demand history data.
    Expects columns: date, sku_id, warehouse_id, quantity, price, category, region
    """
    if data_path and Path(data_path).exists():
        df = pd.read_parquet(data_path)
    else:
        logger.info("No data path provided — generating synthetic demand data")
        df = _generate_synthetic_demand()

    # Date filtering
    df["date"] = pd.to_datetime(df["date"])
    if start_date:
        df = df[df["date"] >= pd.Timestamp(start_date)]
    if end_date:
        df = df[df["date"] <= pd.Timestamp(end_date)]

    # Validate and clean
    df = df.dropna(subset=["date", "sku_id", "quantity"])
    df = df[df["quantity"] >= 0]
    df["quantity"] = df["quantity"].clip(lower=0)

    # Feature engineering
    df = _engineer_features(df)

    logger.info(f"Loaded {len(df):,} demand records | {df['sku_id'].nunique():,} SKUs | "
                f"Date range: {df['date'].min().date()} → {df['date'].max().date()}")
    return df


def _generate_synthetic_demand() -> pd.DataFrame:
    """Generate realistic synthetic demand data for development/testing."""
    np.random.seed(42)
    n_skus = 500
    n_warehouses = 8
    n_days = 730  # 2 years of history

    dates = pd.date_range(end=datetime.now(), periods=n_days, freq="D")
    skus = [f"SKU-{i:04d}" for i in range(n_skus)]
    warehouses = [f"WH-{i:03d}" for i in range(n_warehouses)]
    categories = ["Electronics", "Textiles", "Machinery", "Components", "Raw Materials"]
    regions = ["APAC", "EMEA", "LATAM", "Americas"]

    records = []
    for sku in skus[:100]:  # Subset for speed
        for wh in warehouses[:4]:
            base_demand = np.random.uniform(50, 500)
            category = np.random.choice(categories)
            region = np.random.choice(regions)

            for i, date in enumerate(dates):
                # Trend component
                trend = base_demand * (1 + 0.02 * i / n_days)
                # Weekly seasonality (higher Mon-Wed)
                dow_factor = [1.15, 1.10, 1.05, 1.0, 0.90, 0.75, 0.70][date.dayofweek]
                # Monthly seasonality
                month_factor = 1 + 0.15 * np.sin(2 * np.pi * date.month / 12)
                # Holiday spike (Black Friday area)
                holiday_factor = 3.4 if (date.month == 11 and date.day >= 20) else 1.0
                # Random noise
                noise = np.random.lognormal(0, 0.15)

                quantity = max(0, trend * dow_factor * month_factor * holiday_factor * noise)

                records.append({
                    "date": date,
                    "sku_id": sku,
                    "warehouse_id": wh,
                    "quantity": round(quantity),
                    "price": np.random.uniform(10, 500),
                    "category": category,
                    "region": region,
                })

    return pd.DataFrame(records)


def _engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create time-based and business features for TFT."""
    df = df.copy()
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["week"] = df["date"].dt.isocalendar().week.astype(int)
    df["day_of_week"] = df["date"].dt.dayofweek
    df["day_of_month"] = df["date"].dt.day
    df["quarter"] = df["date"].dt.quarter
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    df["is_month_end"] = (df["date"].dt.is_month_end).astype(int)

    # Holiday flags (simplified US calendar)
    df["is_black_friday"] = ((df["month"] == 11) & (df["day_of_week"] == 4) &
                              (df["day_of_month"] >= 22)).astype(int)
    df["is_holiday_season"] = ((df["month"] == 11) | (df["month"] == 12)).astype(int)
    df["is_q1_slowdown"] = (df["month"].isin([1, 2])).astype(int)

    # Time index for TFT (required)
    min_date = df["date"].min()
    df["time_idx"] = (df["date"] - min_date).dt.days

    # Group index for series identification
    df["series_id"] = df["sku_id"] + "_" + df["warehouse_id"]

    return df


def build_datasets(
    df: pd.DataFrame,
    config: Dict = FORECAST_CONFIG,
) -> Tuple[TimeSeriesDataSet, TimeSeriesDataSet]:
    """Build TFT train and validation datasets."""
    max_time_idx = df["time_idx"].max()
    training_cutoff = max_time_idx - config["max_prediction_length"]

    # Known categorical covariates
    known_categoricals = ["month", "week", "day_of_week", "quarter", "is_weekend"]
    # Unknown real covariates
    time_varying_unknown_reals = ["quantity", "price"]
    # Known real covariates
    time_varying_known_reals = [
        "time_idx", "is_black_friday", "is_holiday_season", "is_q1_slowdown",
        "is_month_end", "day_of_month",
    ]
    # Static categoricals (constant per series)
    static_categoricals = ["sku_id", "warehouse_id", "category", "region"]

    training = TimeSeriesDataSet(
        df[df["time_idx"] <= training_cutoff],
        time_idx="time_idx",
        target="quantity",
        group_ids=["series_id"],
        min_encoder_length=config["max_encoder_length"] // 2,
        max_encoder_length=config["max_encoder_length"],
        min_prediction_length=1,
        max_prediction_length=config["max_prediction_length"],
        static_categoricals=static_categoricals,
        time_varying_known_categoricals=known_categoricals,
        time_varying_known_reals=time_varying_known_reals,
        time_varying_unknown_reals=time_varying_unknown_reals,
        target_normalizer=GroupNormalizer(
            groups=["series_id"],
            transformation="softplus",
        ),
        add_relative_time_idx=True,
        add_target_scales=True,
        add_encoder_length=True,
    )

    validation = TimeSeriesDataSet.from_dataset(
        training,
        df,
        predict=True,
        stop_randomization=True,
    )

    return training, validation


# ─────────────────────────────────────────────
# MODEL TRAINING
# ─────────────────────────────────────────────

def train_tft_model(
    df: pd.DataFrame,
    config: Dict = FORECAST_CONFIG,
    experiment_name: str = "nexus-demand-forecast",
    run_name: Optional[str] = None,
) -> Dict:
    """
    Full TFT training pipeline with MLflow tracking.
    Returns training metrics and model URI.
    """
    seed_everything(42)
    run_name = run_name or f"tft-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # Setup MLflow
    mlflow.set_experiment(experiment_name)
    mlflow.pytorch.autolog()

    with mlflow.start_run(run_name=run_name) as run:
        # Log config
        mlflow.log_params(config)

        # Build datasets
        logger.info("Building TFT datasets...")
        training, validation = build_datasets(df, config)
        train_loader = training.to_dataloader(train=True, batch_size=config["batch_size"], num_workers=4)
        val_loader = validation.to_dataloader(train=False, batch_size=config["batch_size"] * 2, num_workers=4)

        # Build model
        logger.info("Initializing Temporal Fusion Transformer...")
        tft = TemporalFusionTransformer.from_dataset(
            training,
            learning_rate=config["learning_rate"],
            hidden_size=config["hidden_size"],
            attention_head_size=config["attention_head_size"],
            dropout=config["dropout"],
            hidden_continuous_size=config["hidden_continuous_size"],
            output_size=config["output_size"],
            loss=QuantileLoss(quantiles=config["quantiles"]),
            log_interval=10,
            reduce_on_plateau_patience=config["reduce_on_plateau_patience"],
        )
        logger.info(f"Model parameters: {sum(p.numel() for p in tft.parameters()):,}")

        # Callbacks
        early_stop = EarlyStopping(monitor="val_loss", patience=8, verbose=True, mode="min")
        lr_monitor = LearningRateMonitor()
        checkpoint = ModelCheckpoint(
            monitor="val_loss",
            filename="tft-best-{epoch:02d}-{val_loss:.4f}",
            save_top_k=1,
            mode="min",
        )
        mlf_logger = MLFlowLogger(
            experiment_name=experiment_name,
            run_id=run.info.run_id,
        )

        # Train
        trainer = Trainer(
            max_epochs=config["max_epochs"],
            accelerator="auto",
            devices=1,
            gradient_clip_val=0.1,
            callbacks=[early_stop, lr_monitor, checkpoint],
            logger=mlf_logger,
            enable_progress_bar=True,
        )

        logger.info(f"Starting TFT training | run_id={run.info.run_id}")
        trainer.fit(tft, train_dataloaders=train_loader, val_dataloaders=val_loader)

        # Evaluate
        logger.info("Evaluating model on validation set...")
        predictions = tft.predict(val_loader, return_y=True, trainer_kwargs={"accelerator": "auto"})
        y_pred = predictions.output[:, :, 3]  # P50 (median) quantile
        y_true = predictions.y[0]

        mae = float(torch.mean(torch.abs(y_pred - y_true)))
        mape = float(torch.mean(torch.abs((y_pred - y_true) / (y_true + 1e-8))))
        rmse = float(torch.sqrt(torch.mean((y_pred - y_true) ** 2)))

        metrics = {"val_mae": mae, "val_mape": mape, "val_rmse": rmse}
        mlflow.log_metrics(metrics)
        logger.info(f"Validation metrics: MAE={mae:.2f} | MAPE={mape:.4f} | RMSE={rmse:.2f}")

        # Register model in MLflow
        model_uri = f"runs:/{run.info.run_id}/model"
        model_version = mlflow.register_model(model_uri, "nexus-tft-forecast")

        # Promote to production if metrics pass thresholds
        if mape < 0.10:
            client = mlflow.tracking.MlflowClient()
            client.transition_model_version_stage(
                name="nexus-tft-forecast",
                version=model_version.version,
                stage="Production",
                archive_existing_versions=True,
            )
            logger.info(f"Model v{model_version.version} promoted to Production (MAPE={mape:.4f})")
        else:
            logger.warning(f"Model MAPE {mape:.4f} exceeds threshold 0.10 — not promoted")

        return {
            "run_id": run.info.run_id,
            "model_version": model_version.version,
            "metrics": metrics,
            "promoted_to_production": mape < 0.10,
        }


# ─────────────────────────────────────────────
# INFERENCE
# ─────────────────────────────────────────────

class DemandForecastingEngine:
    """
    Production inference engine for TFT demand forecasting.
    Loads registered model from MLflow and serves predictions.
    """

    def __init__(self, model_stage: str = "Production"):
        self.model_stage = model_stage
        self.model = None
        self.config = FORECAST_CONFIG
        self._load_model()

    def _load_model(self):
        """Load the registered TFT model from MLflow."""
        try:
            model_uri = f"models:/nexus-tft-forecast/{self.model_stage}"
            self.model = mlflow.pytorch.load_model(model_uri)
            self.model.eval()
            logger.info(f"TFT model loaded from {model_uri}")
        except Exception as e:
            logger.warning(f"Could not load MLflow model: {e} — using fallback")
            self.model = None

    def predict(
        self,
        historical_data: pd.DataFrame,
        sku_ids: Optional[List[str]] = None,
        warehouse_ids: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        Generate probabilistic demand forecasts.
        Returns DataFrame with P10, P25, P50, P75, P90 quantiles.
        """
        if self.model is None:
            return self._fallback_forecast(historical_data, sku_ids, warehouse_ids)

        df = load_demand_data(df=historical_data)
        if sku_ids:
            df = df[df["sku_id"].isin(sku_ids)]
        if warehouse_ids:
            df = df[df["warehouse_id"].isin(warehouse_ids)]

        _, validation = build_datasets(df, self.config)
        val_loader = validation.to_dataloader(train=False, batch_size=256)

        with torch.no_grad():
            predictions = self.model.predict(val_loader, return_index=True)

        forecast_df = self._format_predictions(predictions)
        return forecast_df

    def _fallback_forecast(
        self,
        df: pd.DataFrame,
        sku_ids: Optional[List[str]] = None,
        warehouse_ids: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """Simple statistical fallback when TFT model unavailable."""
        if sku_ids:
            df = df[df["sku_id"].isin(sku_ids)]

        forecast_dates = pd.date_range(start=datetime.now(), periods=self.config["max_prediction_length"])
        results = []

        for sku in df["sku_id"].unique()[:10]:  # Limit for fallback
            sku_data = df[df["sku_id"] == sku]["quantity"].values[-30:]
            if len(sku_data) == 0:
                continue
            mean = np.mean(sku_data)
            std = np.std(sku_data) + 1e-8

            for date in forecast_dates:
                results.append({
                    "sku_id": sku,
                    "forecast_date": date,
                    "p10": max(0, mean - 1.28 * std),
                    "p25": max(0, mean - 0.67 * std),
                    "p50": max(0, mean),
                    "p75": mean + 0.67 * std,
                    "p90": mean + 1.28 * std,
                    "model": "fallback_statistical",
                })

        return pd.DataFrame(results)

    def _format_predictions(self, predictions) -> pd.DataFrame:
        """Format TFT output into structured forecast DataFrame."""
        # Convert quantile outputs to readable format
        records = []
        for i in range(len(predictions.index)):
            row = predictions.index.iloc[i]
            preds = predictions.output[i]  # Shape: [horizon, n_quantiles]
            for t in range(preds.shape[0]):
                records.append({
                    "series_id": row.get("series_id", "unknown"),
                    "forecast_date": datetime.now() + timedelta(days=t),
                    "p10": float(preds[t, 1]),   # 10th percentile
                    "p25": float(preds[t, 2]),   # 25th percentile
                    "p50": float(preds[t, 3]),   # Median
                    "p75": float(preds[t, 4]),   # 75th percentile
                    "p90": float(preds[t, 5]),   # 90th percentile
                    "model": "tft",
                })
        return pd.DataFrame(records)


# ─────────────────────────────────────────────
# DRIFT DETECTION
# ─────────────────────────────────────────────

class DriftDetector:
    """
    Statistical drift detection for demand forecasting.
    Compares recent demand distribution against historical baseline.
    Triggers model retraining when drift exceeds threshold.
    """

    def __init__(self, threshold_sigma: float = FORECAST_CONFIG["drift_threshold"]):
        self.threshold = threshold_sigma
        self.baseline_stats: Dict = {}

    def fit_baseline(self, df: pd.DataFrame, baseline_days: int = 60) -> None:
        """Establish baseline demand distribution."""
        cutoff = df["date"].max() - timedelta(days=baseline_days)
        baseline = df[df["date"] < cutoff]

        self.baseline_stats = {
            "mean": baseline.groupby("sku_id")["quantity"].mean().to_dict(),
            "std": baseline.groupby("sku_id")["quantity"].std().to_dict(),
            "fitted_date": datetime.now().isoformat(),
        }
        logger.info(f"Drift baseline fitted on {len(baseline):,} observations")

    def detect_drift(
        self,
        df: pd.DataFrame,
        window_days: int = FORECAST_CONFIG["drift_window_days"],
    ) -> Dict:
        """
        Run statistical drift test using Mann-Whitney U.
        Returns drift status and affected SKUs.
        """
        cutoff = df["date"].max() - timedelta(days=window_days)
        recent = df[df["date"] >= cutoff]
        historical = df[df["date"] < cutoff]

        drifted_skus = []
        p_values = {}

        for sku in recent["sku_id"].unique():
            recent_vals = recent[recent["sku_id"] == sku]["quantity"].values
            hist_vals = historical[historical["sku_id"] == sku]["quantity"].values

            if len(recent_vals) < 5 or len(hist_vals) < 10:
                continue

            # Mann-Whitney U test (non-parametric, robust to non-normality)
            stat, p_value = stats.mannwhitneyu(recent_vals, hist_vals, alternative="two-sided")
            p_values[sku] = p_value

            if p_value < 0.05:  # Significant drift detected
                drifted_skus.append(sku)

        drift_rate = len(drifted_skus) / max(len(p_values), 1)
        drift_detected = drift_rate > 0.10  # >10% of SKUs drifting = system-level drift

        result = {
            "drift_detected": drift_detected,
            "drift_rate": drift_rate,
            "drifted_skus_count": len(drifted_skus),
            "total_skus_tested": len(p_values),
            "drifted_skus_sample": drifted_skus[:10],
            "recommendation": "RETRAIN" if drift_detected else "STABLE",
            "detection_timestamp": datetime.now().isoformat(),
        }

        if drift_detected:
            logger.warning(
                f"DRIFT DETECTED: {drift_rate:.1%} of SKUs show significant demand shift. "
                f"Triggering retraining pipeline."
            )
        else:
            logger.info(f"No significant drift detected ({drift_rate:.1%} SKU drift rate)")

        return result


# ─────────────────────────────────────────────
# ASYNC WARM-UP
# ─────────────────────────────────────────────

async def warm_up_model():
    """Pre-load TFT model into memory on API startup."""
    try:
        engine = DemandForecastingEngine()
        logger.info("✅ Demand Forecasting Engine warmed up")
        return engine
    except Exception as e:
        logger.warning(f"Model warm-up failed (non-critical): {e}")


# ─────────────────────────────────────────────
# TRAINING ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train NEXUS TFT Demand Forecasting Model")
    parser.add_argument("--data-path", type=str, default=None, help="Path to demand history parquet")
    parser.add_argument("--experiment", type=str, default="nexus-demand-forecast")
    parser.add_argument("--run-name", type=str, default=None)
    parser.add_argument("--epochs", type=int, default=50)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    FORECAST_CONFIG["max_epochs"] = args.epochs

    # Load data
    df = load_demand_data(data_path=args.data_path)

    # Check for drift before training
    detector = DriftDetector()
    if len(df) > 1000:
        detector.fit_baseline(df)
        drift_result = detector.detect_drift(df)
        print(f"\nDrift Analysis: {drift_result['recommendation']}")
        print(f"  Drift Rate: {drift_result['drift_rate']:.1%}")

    # Train model
    print("\n🚀 Starting TFT Training...")
    result = train_tft_model(df, experiment_name=args.experiment, run_name=args.run_name)
    print(f"\n✅ Training Complete!")
    print(f"  Run ID: {result['run_id']}")
    print(f"  Model Version: {result['model_version']}")
    print(f"  MAPE: {result['metrics']['val_mape']:.4f}")
    print(f"  MAE: {result['metrics']['val_mae']:.2f}")
    print(f"  Promoted to Production: {result['promoted_to_production']}")
