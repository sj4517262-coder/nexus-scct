import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Float, String, select
from sqlalchemy.ext.asyncio import AsyncSession

from confluent_kafka import Producer

from core.database import Base, get_db
from core.config import settings


router = APIRouter()


# =========================================================
# Database Model
# =========================================================

class ShipmentModel(Base):
    __tablename__ = "shipments"

    id = Column(String, primary_key=True)

    tracking_number = Column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )

    carrier = Column(String(100), nullable=False)

    origin = Column(String(200), nullable=False)

    destination = Column(String(200), nullable=False)

    status = Column(
        String(30),
        nullable=False,
        default="IN_TRANSIT",
        index=True,
    )

    eta = Column(DateTime(timezone=True), nullable=True)

    actual_delivery = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    current_lat = Column(Float, nullable=True)

    current_lon = Column(Float, nullable=True)

    risk_score = Column(
        Float,
        nullable=False,
        default=0.0,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
    )


# =========================================================
# Request / Response Schemas
# =========================================================

class ShipmentCreate(BaseModel):
    tracking_number: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    carrier: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    origin: str = Field(
        ...,
        min_length=1,
        max_length=200,
    )

    destination: str = Field(
        ...,
        min_length=1,
        max_length=200,
    )

    status: str = "IN_TRANSIT"

    eta: Optional[datetime] = None

    current_lat: Optional[float] = None

    current_lon: Optional[float] = None

    risk_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )


class ShipmentUpdate(BaseModel):
    status: Optional[str] = None

    eta: Optional[datetime] = None

    current_lat: Optional[float] = None

    current_lon: Optional[float] = None

    risk_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )


class RerouteRequest(BaseModel):
    new_destination: str = Field(
        ...,
        min_length=1,
        max_length=200,
    )

    reason: Optional[str] = None


class ShipmentResponse(BaseModel):
    id: str
    tracking_number: str
    carrier: str
    origin: str
    destination: str
    status: str
    eta: Optional[datetime]
    actual_delivery: Optional[datetime]
    current_lat: Optional[float]
    current_lon: Optional[float]
    risk_score: float
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# =========================================================
# Kafka Publisher
# =========================================================

def publish_shipment_event(
    shipment: ShipmentModel,
    event_type: str = "shipment.updated",
    extra: Optional[dict] = None,
) -> bool:

    try:
        producer = Producer(
            {
                "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS
            }
        )

        event = {
            "event_type": event_type,
            "shipment_id": shipment.id,
            "tracking_number": shipment.tracking_number,
            "carrier": shipment.carrier,
            "origin": shipment.origin,
            "destination": shipment.destination,
            "status": shipment.status,
            "eta": (
                shipment.eta.isoformat()
                if shipment.eta
                else None
            ),
            "current_lat": shipment.current_lat,
            "current_lon": shipment.current_lon,
            "risk_score": shipment.risk_score,
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        if extra:
            event.update(extra)

        producer.produce(
            "supply-chain.shipments",
            key=shipment.tracking_number,
            value=json.dumps(event).encode("utf-8"),
        )

        producer.flush(5)

        return True

    except Exception as exc:
        print(
            f"Kafka shipment publish failed: {exc}"
        )
        return False


# =========================================================
# GET /shipments
# =========================================================

@router.get(
    "",
    response_model=list[ShipmentResponse],
    summary="List active shipments",
)
async def list_shipments(
    shipment_status: Optional[str] = Query(
        default=None,
        alias="status",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
    db: AsyncSession = Depends(get_db),
):
    query = select(ShipmentModel)

    if shipment_status:
        query = query.where(
            ShipmentModel.status
            == shipment_status.upper()
        )

    query = (
        query
        .order_by(
            ShipmentModel.updated_at.desc()
        )
        .limit(limit)
    )

    result = await db.execute(query)

    return list(result.scalars().all())


# =========================================================
# GET /shipments/{id}
# =========================================================

@router.get(
    "/{shipment_id}",
    response_model=ShipmentResponse,
    summary="Get shipment by ID",
)
async def get_shipment(
    shipment_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ShipmentModel).where(
            ShipmentModel.id == shipment_id
        )
    )

    shipment = result.scalar_one_or_none()

    if shipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shipment not found",
        )

    return shipment


# =========================================================
# POST /shipments
# =========================================================

@router.post(
    "",
    response_model=ShipmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create shipment",
)
async def create_shipment(
    request: ShipmentCreate,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(ShipmentModel).where(
            ShipmentModel.tracking_number
            == request.tracking_number
        )
    )

    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A shipment with this tracking number "
                "already exists"
            ),
        )

    now = datetime.now(timezone.utc)

    shipment = ShipmentModel(
        id=str(uuid.uuid4()),
        tracking_number=request.tracking_number,
        carrier=request.carrier,
        origin=request.origin,
        destination=request.destination,
        status=request.status.upper(),
        eta=request.eta,
        current_lat=request.current_lat,
        current_lon=request.current_lon,
        risk_score=request.risk_score,
        created_at=now,
        updated_at=now,
    )

    db.add(shipment)

    await db.commit()
    await db.refresh(shipment)

    kafka_published = publish_shipment_event(
        shipment,
        event_type="shipment.created",
    )

    print(
        f"Shipment created: "
        f"{shipment.tracking_number} "
        f"| Kafka published: {kafka_published}"
    )

    return shipment


# =========================================================
# PATCH /shipments/{id}
# =========================================================

@router.patch(
    "/{shipment_id}",
    response_model=ShipmentResponse,
    summary="Update shipment",
)
async def update_shipment(
    shipment_id: str,
    request: ShipmentUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ShipmentModel).where(
            ShipmentModel.id == shipment_id
        )
    )

    shipment = result.scalar_one_or_none()

    if shipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shipment not found",
        )

    if request.status is not None:
        shipment.status = request.status.upper()

    if request.eta is not None:
        shipment.eta = request.eta

    if request.current_lat is not None:
        shipment.current_lat = request.current_lat

    if request.current_lon is not None:
        shipment.current_lon = request.current_lon

    if request.risk_score is not None:
        shipment.risk_score = request.risk_score

    shipment.updated_at = datetime.now(timezone.utc)

    if shipment.status == "DELIVERED":
        shipment.actual_delivery = datetime.now(
            timezone.utc
        )

    await db.commit()
    await db.refresh(shipment)

    publish_shipment_event(
        shipment,
        event_type="shipment.updated",
    )

    return shipment


# =========================================================
# POST /shipments/{id}/reroute
# =========================================================

@router.post(
    "/{shipment_id}/reroute",
    response_model=ShipmentResponse,
    summary="Reroute a shipment",
)
async def reroute_shipment(
    shipment_id: str,
    request: RerouteRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ShipmentModel).where(
            ShipmentModel.id == shipment_id
        )
    )

    shipment = result.scalar_one_or_none()

    if shipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shipment not found",
        )

    old_destination = shipment.destination

    shipment.destination = request.new_destination

    shipment.status = "REROUTED"

    shipment.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(shipment)

    publish_shipment_event(
        shipment,
        event_type="shipment.rerouted",
        extra={
            "old_destination": old_destination,
            "new_destination": request.new_destination,
            "reason": request.reason,
        },
    )

    return shipment
