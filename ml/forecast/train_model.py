from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sqlalchemy import create_engine, text
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

from core.config import settings


# =========================================================
# CONFIG
# =========================================================

MODEL_DIR = Path("ml/models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)

MODEL_PATH = MODEL_DIR / "demand_forecast_model.joblib"

FEATURE_COLUMNS = [
    "lag_1",
    "lag_7",
    "lag_14",
    "lag_28",
    "rolling_mean_7",
    "rolling_mean_14",
    "rolling_mean_28",
    "rolling_std_7",
    "day_of_week",
    "day_of_month",
    "month",
    "week_of_year",
    "is_weekend",
]


# =========================================================
# DATABASE
# =========================================================

def get_sync_database_url() -> str:
    """
    NEXUS uses asyncpg for the FastAPI application.

    The training pipeline uses synchronous SQLAlchemy,
    so convert the configured asyncpg URL to psycopg2.
    """

    url = settings.DATABASE_URL

    if "+asyncpg" in url:
        url = url.replace(
            "+asyncpg",
            "+psycopg2",
        )

    return url


def get_engine():
    return create_engine(
        get_sync_database_url(),
        pool_pre_ping=True,
    )


# =========================================================
# LOAD DATA
# =========================================================

def load_data() -> pd.DataFrame:

    engine = get_engine()

    query = text(
        """
        SELECT
            demand_date,
            product_id,
            warehouse_id,
            units_sold,

            lag_1,
            lag_7,
            lag_14,
            lag_28,

            rolling_mean_7,
            rolling_mean_14,
            rolling_mean_28,

            rolling_std_7,

            day_of_week,
            day_of_month,
            month,
            week_of_year,

            is_weekend

        FROM forecast_features

        ORDER BY
            demand_date,
            product_id,
            warehouse_id
        """
    )

    with engine.connect() as connection:
        df = pd.read_sql(
            query,
            connection,
        )

    return df


# =========================================================
# PREPROCESS
# =========================================================

def prepare_data(df: pd.DataFrame) -> pd.DataFrame:

    df = df.copy()

    # PostgreSQL boolean → numeric feature
    df["is_weekend"] = (
        df["is_weekend"]
        .astype(int)
    )

    # Remove rows where the required lag
    # features are unavailable.
    df = df.dropna(
        subset=FEATURE_COLUMNS
    )

    return df


# =========================================================
# TRAIN
# =========================================================

def train():

    print()
    print("=" * 60)
    print("NEXUS DEMAND FORECASTING TRAINING")
    print("=" * 60)

    print("\nLoading forecasting data...")

    df = load_data()

    print(
        f"Raw rows       : {len(df):,}"
    )

    if df.empty:
        raise RuntimeError(
            "forecast_features table is empty."
        )

    df = prepare_data(df)

    print(
        f"Usable rows    : {len(df):,}"
    )

    if len(df) < 100:
        raise RuntimeError(
            "Not enough training data."
        )

    # -----------------------------------------------------
    # TIME-BASED SPLIT
    # -----------------------------------------------------
    #
    # IMPORTANT:
    # Do NOT randomly shuffle time-series data.
    #
    # Earlier data → training
    # Later data  → testing
    #

    split_date = df[
        "demand_date"
    ].quantile(0.80)

    train_df = df[
        df["demand_date"] <= split_date
    ].copy()

    test_df = df[
        df["demand_date"] > split_date
    ].copy()

    print()
    print(
        f"Train period   : "
        f"{train_df['demand_date'].min()} "
        f"→ "
        f"{train_df['demand_date'].max()}"
    )

    print(
        f"Test period    : "
        f"{test_df['demand_date'].min()} "
        f"→ "
        f"{test_df['demand_date'].max()}"
    )

    print(
        f"Train rows     : {len(train_df):,}"
    )

    print(
        f"Test rows      : {len(test_df):,}"
    )

    # -----------------------------------------------------
    # FEATURES / TARGET
    # -----------------------------------------------------

    X_train = train_df[
        FEATURE_COLUMNS
    ]

    y_train = train_df[
        "units_sold"
    ]

    X_test = test_df[
        FEATURE_COLUMNS
    ]

    y_test = test_df[
        "units_sold"
    ]

    # -----------------------------------------------------
    # MODEL
    # -----------------------------------------------------

    print("\nTraining model...")

    model = HistGradientBoostingRegressor(
        max_iter=300,
        learning_rate=0.05,
        max_leaf_nodes=31,
        l2_regularization=1.0,
        random_state=42,
    )

    model.fit(
        X_train,
        y_train,
    )

    # -----------------------------------------------------
    # PREDICTIONS
    # -----------------------------------------------------

    predictions = model.predict(
        X_test
    )

    # Demand cannot be negative.
    predictions = np.maximum(
        predictions,
        0,
    )

    # -----------------------------------------------------
    # EVALUATION
    # -----------------------------------------------------

    mae = mean_absolute_error(
        y_test,
        predictions,
    )

    rmse = np.sqrt(
        mean_squared_error(
            y_test,
            predictions,
        )
    )

    # WAPE
    denominator = np.sum(
        np.abs(y_test)
    )

    if denominator > 0:
        wape = (
            np.sum(
                np.abs(
                    y_test.to_numpy()
                    - predictions
                )
            )
            / denominator
        ) * 100
    else:
        wape = 0.0

    print()
    print("=" * 60)
    print("MODEL RESULTS")
    print("=" * 60)

    print(
        f"MAE            : {mae:.2f}"
    )

    print(
        f"RMSE           : {rmse:.2f}"
    )

    print(
        f"WAPE           : {wape:.2f}%"
    )

    print("=" * 60)

    # -----------------------------------------------------
    # SAVE MODEL
    # -----------------------------------------------------

    model_data = {
        "model": model,
        "features": FEATURE_COLUMNS,

        "mae": float(mae),
        "rmse": float(rmse),
        "wape": float(wape),

        "trained_rows": int(
            len(train_df)
        ),

        "test_rows": int(
            len(test_df)
        ),

        "train_start": str(
            train_df["demand_date"].min()
        ),

        "train_end": str(
            train_df["demand_date"].max()
        ),

        "test_start": str(
            test_df["demand_date"].min()
        ),

        "test_end": str(
            test_df["demand_date"].max()
        ),
    }

    joblib.dump(
        model_data,
        MODEL_PATH,
    )

    print()
    print(
        f"Model saved    : {MODEL_PATH}"
    )

    print()


if __name__ == "__main__":
    train()