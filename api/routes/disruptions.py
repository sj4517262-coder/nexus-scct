import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db, DisruptionModel


router = APIRouter()


# =========================================================
# Pydantic Schemas
# =========================================================

class DisruptionCreate(BaseModel):
    event_type: str = Field(
        default="supply_disruption",
        max_length=50,
    )

    severity: str = Field(
        default="medium",
        max_length=20,
    )

    title: str = Field(
        min_length=1,
        max_length=200,
    )

    description: Optional[str] = None

    affected_entities: list = Field(
        default_factory=list,
    )

    estimated_impact_usd: Optional[float] = None

    metadata: dict = Field(
        default_factory=dict,
    )


class DisruptionStatusUpdate(BaseModel):
    status: str = Field(
        ...,
        description="ACTIVE, INVESTIGATING, MITIGATED, or RESOLVED",
    )


class DisruptionResponse(BaseModel):
    id: str
    event_id: str
    event_type: str
    severity: str
    title: str
    description: Optional[str]
    affected_entities: list
    estimated_impact_usd: Optional[float]
    status: str
    orchestration_id: Optional[str]

    metadata: dict = Field(
        default_factory=dict,
        validation_alias="metadata_",
    )

    detected_at: Optional[datetime]
    resolved_at: Optional[datetime]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True
        populate_by_name = True


# =========================================================
# Kafka Publisher
# =========================================================

def publish_disruption_event(
    disruption: DisruptionModel,
) -> bool:
    """
    Publish a disruption event through the central NEXUS
    Kafka producer.

    IMPORTANT:
    The central producer in streaming_layer.py creates the
    standard Kafka envelope:

        {
            "event_id": "...",
            "event_type": "...",
            "source": "...",
            "timestamp": "...",
            "schema_version": "2.0",
            "payload": {...}
        }

    The Kafka consumer expects this envelope and extracts:

        payload = envelope["payload"]

    Therefore we must NOT publish a raw payload directly here.
    """

    try:
        from streaming_layer import get_producer

        payload = {
            "event_id": disruption.event_id,
            "disruption_id": disruption.id,
            "event_type": disruption.event_type,
            "severity": disruption.severity,
            "title": disruption.title,
            "description": disruption.description,
            "affected_entities": (
                disruption.affected_entities or []
            ),
            "estimated_impact_usd": (
                disruption.estimated_impact_usd
            ),
            "status": disruption.status,
            "detected_at": (
                disruption.detected_at.isoformat()
                if disruption.detected_at
                else None
            ),
            "metadata": (
                disruption.metadata_
                if disruption.metadata_
                else {}
            ),
        }

        producer = get_producer()

        # The central producer creates the correct envelope.
        return producer.produce_disruption(payload)

    except Exception as exc:
        print(
            f"Kafka disruption publish failed: {exc}"
        )
        return False


# =========================================================
# GET /disruptions
# =========================================================

@router.get(
    "",
    response_model=list[DisruptionResponse],
    summary="List supply chain disruptions",
)
async def list_disruptions(
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
    ),
    severity: Optional[str] = None,
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
    db: AsyncSession = Depends(get_db),
):
    query = select(DisruptionModel)

    # Filter by status
    if status_filter:
        query = query.where(
            DisruptionModel.status
            == status_filter.upper()
        )

    # Filter by severity
    if severity:
        query = query.where(
            DisruptionModel.severity
            == severity.lower()
        )

    query = (
        query
        .order_by(
            DisruptionModel.created_at.desc()
        )
        .limit(limit)
    )

    result = await db.execute(query)

    return list(result.scalars().all())


# =========================================================
# GET /disruptions/{disruption_id}
# =========================================================

@router.get(
    "/{disruption_id}",
    response_model=DisruptionResponse,
    summary="Get a disruption by ID",
)
async def get_disruption(
    disruption_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DisruptionModel).where(
            DisruptionModel.id == disruption_id
        )
    )

    disruption = result.scalar_one_or_none()

    if disruption is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Disruption not found",
        )

    return disruption


# =========================================================
# POST /disruptions
# =========================================================

@router.post(
    "",
    response_model=DisruptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a supply chain disruption",
)
async def create_disruption(
    request: DisruptionCreate,
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)

    # Normalize severity
    severity = request.severity.strip().lower()

    allowed_severities = {
        "low",
        "medium",
        "high",
        "critical",
    }

    if severity not in allowed_severities:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Invalid severity. Allowed values: "
                "low, medium, high, critical"
            ),
        )

    # Normalize event type
    event_type = (
        request.event_type
        .strip()
        .lower()
    )

    # Create database record
    disruption = DisruptionModel(
        id=str(uuid.uuid4()),

        event_id=(
            f"DIS-{uuid.uuid4().hex[:12].upper()}"
        ),

        event_type=event_type,

        severity=severity,

        title=request.title,

        description=request.description,

        affected_entities=(
            request.affected_entities
        ),

        estimated_impact_usd=(
            request.estimated_impact_usd
        ),

        status="ACTIVE",

        metadata_=request.metadata,

        detected_at=now,

        created_at=now,
    )

    db.add(disruption)

    # Save to PostgreSQL
    await db.commit()

    # Refresh so all generated fields are available
    await db.refresh(disruption)

    # Publish the SAME disruption to Kafka
    kafka_published = publish_disruption_event(
        disruption
    )

    print(
        f"Disruption created: "
        f"{disruption.event_id} "
        f"| severity={disruption.severity} "
        f"| Kafka published={kafka_published}"
    )

    return disruption


# =========================================================
# PATCH /disruptions/{disruption_id}/status
# =========================================================

@router.patch(
    "/{disruption_id}/status",
    response_model=DisruptionResponse,
    summary="Update disruption status",
)
async def update_disruption_status(
    disruption_id: str,
    request: DisruptionStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DisruptionModel).where(
            DisruptionModel.id == disruption_id
        )
    )

    disruption = result.scalar_one_or_none()

    if disruption is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Disruption not found",
        )

    new_status = (
        request.status
        .strip()
        .upper()
    )

    allowed_statuses = {
        "ACTIVE",
        "INVESTIGATING",
        "MITIGATED",
        "RESOLVED",
    }

    if new_status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Invalid status. Allowed values: "
                + ", ".join(
                    sorted(allowed_statuses)
                )
            ),
        )

    disruption.status = new_status

    if new_status == "RESOLVED":
        disruption.resolved_at = (
            datetime.now(timezone.utc)
        )
    else:
        disruption.resolved_at = None

    # Save status update
    await db.commit()

    await db.refresh(disruption)

    # Publish updated disruption state to Kafka
    kafka_published = publish_disruption_event(
        disruption
    )

    print(
        f"Disruption status updated: "
        f"{disruption.event_id} "
        f"| status={disruption.status} "
        f"| Kafka published={kafka_published}"
    )

    return disruption