from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ml.forecast.tft_model import DemandForecastingEngine

router = APIRouter()


class ForecastPoint(BaseModel):
    sku_id: str
    forecast_date: str
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float
    model: str


_engine: Optional[DemandForecastingEngine] = None


def _get_engine() -> DemandForecastingEngine:
    global _engine

    if _engine is None:
        _engine = DemandForecastingEngine()

    return _engine


def _build_demo_history(
    sku_id: str,
    warehouse_id: str,
    days: int = 60,
) -> pd.DataFrame:
    """
    Create a small development dataset for the forecast API.

    The full TFT training pipeline can use real historical demand data.
    For the API demo, we generate 60 days of realistic demand history.
    """

    end_date = datetime.utcnow().date()
    dates = [
        end_date - timedelta(days=days - 1 - i)
        for i in range(days)
    ]

    rows = []

    for i, date in enumerate(dates):
        base_demand = 100

        weekly_effect = 15 if date.weekday() in (4, 5) else 0

        seasonal_effect = 10 * (
            __import__("math").sin(i / 7)
        )

        quantity = max(
            20,
            round(
                base_demand
                + weekly_effect
                + seasonal_effect
                + (i * 0.2)
            ),
        )

        rows.append(
            {
                "date": pd.Timestamp(date),
                "sku_id": sku_id,
                "warehouse_id": warehouse_id,
                "quantity": quantity,
                "price": 100.0,
                "category": "apparel",
                "region": "north",
            }
        )

    return pd.DataFrame(rows)


@router.get(
    "",
    response_model=list[ForecastPoint],
    summary="Demand forecast",
)
async def get_forecast(
    horizon: int = Query(
        default=28,
        ge=1,
        le=90,
        description="Number of days to forecast",
    ),
    sku_id: str = Query(
        default="SKU-JEANS-001",
        description="SKU to forecast",
    ),
    warehouse_id: str = Query(
        default="WH-DELHI-001",
        description="Warehouse to forecast",
    ),
):
    """
    Generate a demand forecast.

    The API uses the existing NEXUS forecasting engine.
    If an MLflow TFT model is not registered, the engine
    automatically uses its fallback forecasting method.
    """

    try:
        engine = _get_engine()

        history = _build_demo_history(
            sku_id=sku_id,
            warehouse_id=warehouse_id,
        )

        result = engine.predict(
            historical_data=history,
            sku_ids=[sku_id],
            warehouse_ids=[warehouse_id],
        )

        if result is None or result.empty:
            raise HTTPException(
                status_code=404,
                detail="No forecast could be generated",
            )

        result = result.head(horizon)

        return [
            ForecastPoint(
                sku_id=str(row["sku_id"]),
                forecast_date=str(row["forecast_date"]),
                p10=float(row["p10"]),
                p25=float(row["p25"]),
                p50=float(row["p50"]),
                p75=float(row["p75"]),
                p90=float(row["p90"]),
                model=str(row["model"]),
            )
            for _, row in result.iterrows()
        ]

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Forecast generation failed: {exc}",
        )
