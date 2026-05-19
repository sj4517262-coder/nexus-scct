"""
NEXUS — Core Platform Modules
Configuration, Security (JWT/RBAC), Database, and Logging
"""

# ═══════════════════════════════════════════════
# core/config.py
# ═══════════════════════════════════════════════
from functools import lru_cache
from typing import List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "NEXUS Supply Chain Control Tower"
    VERSION: str = "2.4.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://nexus:password@localhost:5432/nexus_db"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 40
    DATABASE_POOL_TIMEOUT: int = 30

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL: int = 3600

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_CONSUMER_GROUP_ID: str = "nexus-consumers"
    KAFKA_AUTO_OFFSET_RESET: str = "earliest"

    # Security
    SECRET_KEY: str = "change-this-to-a-secure-random-string-minimum-32-chars"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # AI APIs
    ANTHROPIC_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    LLM_PRIMARY_MODEL: str = "claude-sonnet-4-20250514"
    LLM_FALLBACK_MODEL: str = "gpt-4-turbo-preview"
    LLM_MAX_TOKENS: int = 4096
    LLM_TEMPERATURE: float = 0.1

    # Agent Config
    AGENT_AUTO_APPROVE_THRESHOLD: float = 0.85
    AGENT_MAX_VALUE_AUTO_APPROVE: float = 1_000_000.0
    AGENT_ORCHESTRATION_TIMEOUT: int = 180
    AGENT_MAX_RETRIES: int = 3

    # MLflow
    MLFLOW_TRACKING_URI: str = "http://localhost:5000"
    MLFLOW_EXPERIMENT_NAME: str = "nexus-supply-chain"

    # CORS & Rate Limiting
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]
    RATE_LIMIT_PER_MINUTE: int = 100
    RATE_LIMIT_BURST: int = 20

    # Notifications
    SLACK_WEBHOOK_URL: Optional[str] = None
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    EMAIL_FROM: Optional[str] = None

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v):
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()


# ═══════════════════════════════════════════════
# core/security.py
# ═══════════════════════════════════════════════
import time
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, Optional

from fastapi import HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from starlette.middleware.base import BaseHTTPMiddleware

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


class UserRole(str, Enum):
    VIEWER = "VIEWER"
    OPERATOR = "OPERATOR"
    MANAGER = "MANAGER"
    EXECUTIVE = "EXECUTIVE"
    ADMIN = "ADMIN"


class TokenPayload:
    def __init__(self, sub: str, role: UserRole, exp: datetime, jti: str):
        self.sub = sub
        self.role = role
        self.exp = exp
        self.jti = jti


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    subject: str,
    role: UserRole = UserRole.OPERATOR,
    expires_delta: Optional[timedelta] = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": subject,
        "role": role.value,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),
        "iss": "nexus-control-tower",
        "type": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_token(token: str) -> Dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") not in ["access", None]:
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_role(*allowed_roles: UserRole):
    """Dependency: require specific user roles for endpoint access."""
    def check_role(credentials: HTTPAuthorizationCredentials = security):
        payload = verify_token(credentials.credentials)
        user_role = UserRole(payload.get("role", "VIEWER"))
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {[r.value for r in allowed_roles]}. "
                       f"Your role: {user_role.value}",
            )
        return payload
    return check_role


# ─── Rate Limiting Middleware ──────────────────
class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token bucket rate limiting middleware with per-user tracking."""

    def __init__(self, app, rate_limit: int = 100, burst_limit: int = 20):
        super().__init__(app)
        self.rate_limit = rate_limit
        self.burst_limit = burst_limit
        self._buckets: Dict[str, Dict] = {}

    def _get_client_id(self, request: Request) -> str:
        # Use JWT subject if authenticated, else IP
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            try:
                payload = verify_token(auth[7:])
                return f"user:{payload.get('sub', 'unknown')}"
            except Exception:
                pass
        return f"ip:{request.client.host}"

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)

        client_id = self._get_client_id(request)
        now = time.time()

        if client_id not in self._buckets:
            self._buckets[client_id] = {"tokens": self.rate_limit, "last_refill": now}

        bucket = self._buckets[client_id]
        elapsed = now - bucket["last_refill"]
        refill = elapsed * (self.rate_limit / 60)
        bucket["tokens"] = min(self.rate_limit, bucket["tokens"] + refill)
        bucket["last_refill"] = now

        if bucket["tokens"] < 1:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "limit": self.rate_limit,
                    "window": "60s",
                    "retry_after_seconds": round((1 - bucket["tokens"]) * 60 / self.rate_limit),
                },
                headers={
                    "X-RateLimit-Limit": str(self.rate_limit),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": str(int((1 - bucket["tokens"]) * 60 / self.rate_limit)),
                },
            )

        bucket["tokens"] -= 1
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.rate_limit)
        response.headers["X-RateLimit-Remaining"] = str(int(bucket["tokens"]))
        return response


# ═══════════════════════════════════════════════
# core/database.py
# ═══════════════════════════════════════════════
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, String, DateTime, Float, Integer, Boolean, Text, JSON

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


# ── ORM Models ─────────────────────────────────
class DisruptionModel(Base):
    __tablename__ = "disruptions"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String, unique=True, nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    affected_entities = Column(JSON, default=list)
    estimated_impact_usd = Column(Float)
    status = Column(String(20), default="ACTIVE", index=True)
    orchestration_id = Column(String)
    metadata_ = Column("metadata", JSON, default=dict)
    detected_at = Column(DateTime(timezone=True))
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True))


class AgentDecisionModel(Base):
    __tablename__ = "agent_decisions"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    decision_id = Column(String, unique=True, nullable=False, index=True)
    orchestration_id = Column(String, index=True)
    agent_type = Column(String(50), nullable=False)
    decision_type = Column(String(100))
    action = Column(Text, nullable=False)
    reasoning = Column(Text)
    confidence = Column(Float, nullable=False)
    estimated_value_usd = Column(Float)
    risk_level = Column(String(20))
    status = Column(String(30), default="PROPOSED", index=True)
    requires_human_approval = Column(Boolean, default=False)
    approver_id = Column(String, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approval_reason = Column(Text, nullable=True)
    alternatives_considered = Column(JSON, default=list)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True))
    executed_at = Column(DateTime(timezone=True), nullable=True)


class SupplierModel(Base):
    __tablename__ = "suppliers"
    id = Column(String, primary_key=True)
    name = Column(String(200), nullable=False, index=True)
    country = Column(String(100), nullable=False)
    region = Column(String(50), index=True)
    category = Column(String(100))
    risk_level = Column(String(20), index=True)
    risk_score = Column(Integer)
    on_time_delivery_rate = Column(Float)
    monthly_volume_units = Column(Integer)
    annual_spend_usd = Column(Integer)
    tier = Column(Integer)
    certifications = Column(JSON, default=list)
    last_scored_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True))


class KPISnapshotModel(Base):
    __tablename__ = "kpi_snapshots"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    otif_pct = Column(Float)
    fill_rate_pct = Column(Float)
    inventory_turnover = Column(Float)
    warehouse_utilization_pct = Column(Float)
    transport_cost_per_unit = Column(Float)
    stockout_probability_pct = Column(Float)
    supplier_reliability_pct = Column(Float)
    delay_risk_pct = Column(Float)
    ai_decisions_count = Column(Integer)
    ai_auto_approve_rate = Column(Float)
    active_disruptions = Column(Integer)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_connection() -> bool:
    from sqlalchemy import text
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════
# core/logging_config.py
# ═══════════════════════════════════════════════
import logging
import sys
import structlog


def setup_logging():
    """Configure structured JSON logging for production."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if settings.ENVIRONMENT != "development"
            else structlog.dev.ConsoleRenderer(colors=True),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Silence noisy libraries
    for noisy_lib in ["uvicorn.access", "sqlalchemy.engine", "confluent_kafka"]:
        logging.getLogger(noisy_lib).setLevel(logging.WARNING)

    logging.info(f"Logging configured | level={settings.LOG_LEVEL} | env={settings.ENVIRONMENT}")
