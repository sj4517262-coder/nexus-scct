"""
NEXUS Supply Chain Control Tower — FastAPI Backend
Production-grade enterprise API with WebSocket streaming,
multi-agent orchestration, and real-time event processing.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from api.routes import (
    auth,
    disruptions,
    inventory,
    kpis,
    shipments,
    suppliers,
    agents,
    forecast,
)
from api.websocket import router as ws_router
from core.config import settings
from core.database import engine, Base
from core.logging_config import setup_logging
from core.security import RateLimitMiddleware
from streaming.kafka_consumer import start_kafka_consumers
from workers.celery_app import celery_app

# ─────────────────────────────────────────────
# Logging Setup
# ─────────────────────────────────────────────
setup_logging()
logger = logging.getLogger("nexus.api")


# ─────────────────────────────────────────────
# Application Lifespan
# ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Manage application startup and shutdown lifecycle."""
    logger.info("🚀 NEXUS Control Tower — Starting up...")

    # Initialize database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Database tables initialized")

    # Start Kafka consumers (background task)
    consumer_task = asyncio.create_task(start_kafka_consumers())
    logger.info("✅ Kafka consumers started")

    # Warm up ML model cache
    try:
        from ml.forecast.tft_model import warm_up_model
        await warm_up_model()
        logger.info("✅ ML model cache warmed up")
    except Exception as e:
        logger.warning(f"⚠️  ML model warm-up skipped: {e}")

    logger.info("✅ NEXUS Control Tower — Ready to serve")

    yield  # Application is running

    # Shutdown
    logger.info("🛑 NEXUS Control Tower — Shutting down...")
    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass
    await engine.dispose()
    logger.info("✅ Shutdown complete")


# ─────────────────────────────────────────────
# FastAPI Application
# ─────────────────────────────────────────────
app = FastAPI(
    title="NEXUS Supply Chain Control Tower",
    description="""
    ## Autonomous Supply Chain Control Tower API

    Enterprise-grade AI platform for supply chain monitoring,
    disruption prediction, and autonomous decision orchestration.

    ### Key Capabilities
    - 🤖 Multi-agent AI orchestration (8 specialized agents)
    - ⚡ Real-time Kafka event streaming
    - 📈 TFT demand forecasting (28-day horizon)
    - ⚠️  Supplier risk intelligence (XGBoost scoring)
    - 🚢 Route optimization (OR-Tools VRP solver)
    - 📦 RL-based inventory optimization
    - 👤 Human-in-the-loop approval workflows
    """,
    version="2.4.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


# ─────────────────────────────────────────────
# Middleware Stack
# ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    RateLimitMiddleware,
    rate_limit=settings.RATE_LIMIT_PER_MINUTE,
    burst_limit=settings.RATE_LIMIT_BURST,
)


# ─────────────────────────────────────────────
# Request Logging & Tracing Middleware
# ─────────────────────────────────────────────
@app.middleware("http")
async def request_tracing_middleware(request: Request, call_next):
    """Log all requests with timing and correlation IDs."""
    import uuid
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    start_time = time.perf_counter()

    # Inject correlation ID into request state
    request.state.correlation_id = correlation_id

    try:
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "HTTP Request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "correlation_id": correlation_id,
            },
        )

        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
        return response

    except Exception as exc:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.error(
            f"Request failed: {exc}",
            extra={"correlation_id": correlation_id, "duration_ms": duration_ms},
            exc_info=True,
        )
        raise


# ─────────────────────────────────────────────
# Global Exception Handlers
# ─────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "correlation_id": correlation_id,
            "message": str(exc) if settings.DEBUG else "An unexpected error occurred",
        },
    )


# ─────────────────────────────────────────────
# Route Registration
# ─────────────────────────────────────────────
API_V1_PREFIX = "/api/v1"

app.include_router(auth.router, prefix=f"{API_V1_PREFIX}/auth", tags=["Authentication"])
app.include_router(disruptions.router, prefix=f"{API_V1_PREFIX}/disruptions", tags=["Disruptions"])
app.include_router(inventory.router, prefix=f"{API_V1_PREFIX}/inventory", tags=["Inventory"])
app.include_router(suppliers.router, prefix=f"{API_V1_PREFIX}/suppliers", tags=["Suppliers"])
app.include_router(shipments.router, prefix=f"{API_V1_PREFIX}/shipments", tags=["Shipments"])
app.include_router(kpis.router, prefix=f"{API_V1_PREFIX}/kpis", tags=["KPIs"])
app.include_router(agents.router, prefix=f"{API_V1_PREFIX}/agents", tags=["AI Agents"])
app.include_router(forecast.router, prefix=f"{API_V1_PREFIX}/forecast", tags=["Forecasting"])
app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])


# ─────────────────────────────────────────────
# Health & Status Endpoints
# ─────────────────────────────────────────────
@app.get("/health", tags=["Health"], summary="Platform health check")
async def health_check():
    """Comprehensive health check for load balancers and monitoring."""
    from core.database import check_db_connection
    from core.redis_client import check_redis_connection
    from streaming.kafka_producer import check_kafka_connection

    checks = {
        "database": await check_db_connection(),
        "redis": await check_redis_connection(),
        "kafka": await check_kafka_connection(),
        "celery": celery_app.control.ping(timeout=1) is not None,
    }

    all_healthy = all(checks.values())
    return JSONResponse(
        status_code=status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "healthy" if all_healthy else "degraded",
            "version": "2.4.0",
            "environment": settings.ENVIRONMENT,
            "checks": checks,
            "timestamp": time.time(),
        },
    )


@app.get("/", tags=["Root"])
async def root():
    return {
        "platform": "NEXUS Supply Chain Control Tower",
        "version": "2.4.0",
        "status": "operational",
        "docs": "/docs",
        "health": "/health",
    }


# ─────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        workers=settings.WORKERS,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=True,
    )
