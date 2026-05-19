"""
NEXUS — API Routes Layer
REST endpoints for all supply chain entities.
Organized as modular FastAPI routers.
"""

# ═══════════════════════════════════════════════
# backend/api/routes/disruptions.py
# ═══════════════════════════════════════════════
from __future__ import annotations
import uuid, logging
from datetime import datetime, timezone
from typing import List, Optional
from enum import Enum

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("nexus.api.disruptions")
router = APIRouter()


# ── Models ─────────────────────────────────────
class SeverityEnum(str, Enum):
    LOW = "LOW"; MEDIUM = "MEDIUM"; HIGH = "HIGH"; CRITICAL = "CRITICAL"

class DisruptionTypeEnum(str, Enum):
    WEATHER = "WEATHER"; GEOPOLITICAL = "GEOPOLITICAL"; SUPPLIER = "SUPPLIER"
    PORT = "PORT"; DEMAND = "DEMAND"; LOGISTICS = "LOGISTICS"

class DisruptionCreate(BaseModel):
    event_type: DisruptionTypeEnum
    severity: SeverityEnum
    title: str = Field(..., min_length=5, max_length=200)
    description: str = Field(..., min_length=10, max_length=2000)
    affected_entities: List[str] = Field(default_factory=list)
    estimated_impact_usd: Optional[float] = Field(None, ge=0)
    metadata: dict = Field(default_factory=dict)

class DisruptionResponse(BaseModel):
    id: str; event_id: str; event_type: str; severity: str
    title: str; description: str; affected_entities: List[str]
    estimated_impact_usd: Optional[float]; status: str
    detected_at: str; resolved_at: Optional[str]
    orchestration_id: Optional[str]
    class Config: from_attributes = True

class OrchestrateResponse(BaseModel):
    orchestration_id: str; event_id: str; status: str
    agents_invoked: List[str]; total_decisions: int
    auto_approved: int; pending_human_approval: int
    escalation_required: bool; total_value_at_stake_usd: float
    executive_summary: Optional[str]

# ── Endpoints ──────────────────────────────────
@router.get("/", response_model=List[DisruptionResponse], summary="List active disruptions")
async def list_disruptions(
    severity: Optional[SeverityEnum] = Query(None),
    event_type: Optional[DisruptionTypeEnum] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    """Return all disruptions with optional filtering. Sorted by severity then recency."""
    # Production: query from PostgreSQL via SQLAlchemy
    # Demo: return synthetic data
    disruptions = _mock_disruptions()
    if severity:
        disruptions = [d for d in disruptions if d["severity"] == severity.value]
    if event_type:
        disruptions = [d for d in disruptions if d["event_type"] == event_type.value]
    return disruptions[offset:offset + limit]

@router.post("/", response_model=OrchestrateResponse, status_code=status.HTTP_201_CREATED,
             summary="Report disruption and trigger AI orchestration")
async def create_disruption(
    disruption: DisruptionCreate,
    background_tasks: BackgroundTasks,
):
    """
    Report a new supply chain disruption.
    Automatically triggers the 8-agent AI orchestration pipeline.
    Returns orchestration results including all agent decisions.
    """
    event_id = str(uuid.uuid4())
    logger.info(f"Disruption reported: {disruption.title} | severity={disruption.severity} | event_id={event_id}")

    # In production: persist to DB, publish to Kafka, then orchestrate
    background_tasks.add_task(
        _publish_disruption_event,
        event_id=event_id,
        disruption=disruption.dict(),
    )

    # Trigger orchestration (production: async via Celery)
    try:
        from agents.orchestrator import DisruptionEvent, get_orchestrator
        event = DisruptionEvent(
            event_id=event_id,
            event_type=disruption.event_type.value,
            severity=disruption.severity.value,
            title=disruption.title,
            description=disruption.description,
            affected_entities=disruption.affected_entities,
            estimated_impact_usd=disruption.estimated_impact_usd or 0,
            metadata=disruption.metadata,
        )
        orchestrator = get_orchestrator()
        result = await orchestrator.handle_disruption(event)
        return OrchestrateResponse(**result)
    except Exception as e:
        logger.error(f"Orchestration failed for event {event_id}: {e}")
        # Return partial response — don't fail the disruption report
        return OrchestrateResponse(
            orchestration_id=str(uuid.uuid4()),
            event_id=event_id,
            status="QUEUED",
            agents_invoked=[],
            total_decisions=0,
            auto_approved=0,
            pending_human_approval=0,
            escalation_required=disruption.severity == SeverityEnum.CRITICAL,
            total_value_at_stake_usd=0.0,
            executive_summary="Orchestration queued — results will be available shortly.",
        )

@router.get("/{disruption_id}", response_model=DisruptionResponse, summary="Get disruption details")
async def get_disruption(disruption_id: str):
    disruptions = _mock_disruptions()
    match = next((d for d in disruptions if d["id"] == disruption_id), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"Disruption {disruption_id} not found")
    return match

@router.patch("/{disruption_id}/resolve", summary="Mark disruption as resolved")
async def resolve_disruption(disruption_id: str, resolution_notes: str = ""):
    logger.info(f"Resolving disruption {disruption_id}")
    return {
        "disruption_id": disruption_id,
        "status": "RESOLVED",
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "resolution_notes": resolution_notes,
    }

async def _publish_disruption_event(event_id: str, disruption: dict):
    """Background task: publish disruption event to Kafka."""
    try:
        from streaming.kafka_producer import get_producer
        producer = get_producer()
        producer.produce(
            topic="supply-chain.disruptions",
            key=event_id,
            value=disruption,
        )
        producer.flush()
        logger.info(f"Disruption event {event_id} published to Kafka")
    except Exception as e:
        logger.error(f"Failed to publish disruption event: {e}")

def _mock_disruptions():
    return [
        {"id": "DISR-0001", "event_id": str(uuid.uuid4()), "event_type": "GEOPOLITICAL",
         "severity": "CRITICAL", "title": "Taiwan Strait Shipping Restriction",
         "description": "Naval exercises restricting commercial shipping through Taiwan Strait",
         "affected_entities": ["S001", "S006", "S008", "P001"],
         "estimated_impact_usd": 45_000_000, "status": "ACTIVE",
         "detected_at": "2024-11-18T12:18:00Z", "resolved_at": None,
         "orchestration_id": str(uuid.uuid4())},
        {"id": "DISR-0002", "event_id": str(uuid.uuid4()), "event_type": "WEATHER",
         "severity": "HIGH", "title": "Typhoon Haikui — East China Sea",
         "description": "Category 3 typhoon tracking across major APAC shipping corridors",
         "affected_entities": ["S001", "S002", "P001", "SHP-00142"],
         "estimated_impact_usd": 8_500_000, "status": "ACTIVE",
         "detected_at": "2024-11-18T10:31:00Z", "resolved_at": None,
         "orchestration_id": str(uuid.uuid4())},
        {"id": "DISR-0003", "event_id": str(uuid.uuid4()), "event_type": "SUPPLIER",
         "severity": "HIGH", "title": "Shenzhen Electronics Factory Shutdown",
         "description": "Fire at Shenzhen Electronics Co. main production facility. Estimated 60-day closure.",
         "affected_entities": ["S001"],
         "estimated_impact_usd": 24_000_000, "status": "ESCALATED",
         "detected_at": "2024-11-18T07:45:00Z", "resolved_at": None,
         "orchestration_id": str(uuid.uuid4())},
    ]


# ═══════════════════════════════════════════════
# backend/api/routes/inventory.py
# ═══════════════════════════════════════════════
from fastapi import APIRouter as InventoryRouter

inventory_router = InventoryRouter()

class WarehouseInventory(BaseModel):
    warehouse_id: str; warehouse_name: str; city: str; region: str
    capacity_units: int; current_inventory_units: int
    utilization_pct: float; status: str
    reorder_point_units: int; safety_stock_units: int
    stockout_probability: float; days_of_supply: float

class OptimizationRequest(BaseModel):
    warehouse_ids: List[str] = Field(default_factory=list)
    optimization_type: str = Field(default="REBALANCE")
    urgency: str = Field(default="NORMAL")
    constraints: dict = Field(default_factory=dict)

class RebalanceRecommendation(BaseModel):
    from_warehouse: str; to_warehouse: str
    quantity: int; sku_category: str
    estimated_cost_usd: float; confidence: float
    urgency: str; ai_reasoning: str

@inventory_router.get("/", response_model=List[WarehouseInventory], summary="Get inventory status all warehouses")
async def get_inventory_status():
    return [
        {"warehouse_id":"W001","warehouse_name":"Chicago Hub","city":"Chicago","region":"Americas",
         "capacity_units":50000,"current_inventory_units":39000,"utilization_pct":78.0,"status":"OPTIMAL",
         "reorder_point_units":15000,"safety_stock_units":7500,"stockout_probability":0.024,"days_of_supply":18.2},
        {"warehouse_id":"W002","warehouse_name":"Dallas DC","city":"Dallas","region":"Americas",
         "capacity_units":45000,"current_inventory_units":40950,"utilization_pct":91.0,"status":"CRITICAL",
         "reorder_point_units":13500,"safety_stock_units":6750,"stockout_probability":0.187,"days_of_supply":12.4},
        {"warehouse_id":"W005","warehouse_name":"Frankfurt Euro","city":"Frankfurt","region":"EMEA",
         "capacity_units":55000,"current_inventory_units":45100,"utilization_pct":82.0,"status":"WARNING",
         "reorder_point_units":16500,"safety_stock_units":8250,"stockout_probability":0.063,"days_of_supply":15.8},
        {"warehouse_id":"W007","warehouse_name":"Singapore APAC","city":"Singapore","region":"APAC",
         "capacity_units":60000,"current_inventory_units":52800,"utilization_pct":88.0,"status":"WARNING",
         "reorder_point_units":18000,"safety_stock_units":9000,"stockout_probability":0.089,"days_of_supply":14.1},
    ]

@inventory_router.post("/optimize", status_code=202, summary="Trigger inventory optimization")
async def trigger_optimization(request: OptimizationRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    logger.info(f"Optimization job queued | id={job_id} | type={request.optimization_type}")
    background_tasks.add_task(_run_rl_optimization, job_id, request.dict())
    return {"job_id": job_id, "status": "QUEUED", "estimated_completion_seconds": 45,
            "optimization_type": request.optimization_type}

@inventory_router.get("/rebalance-recommendations", response_model=List[RebalanceRecommendation])
async def get_rebalance_recommendations():
    return [
        {"from_warehouse":"W001","to_warehouse":"W002","quantity":8400,"sku_category":"Electronics",
         "estimated_cost_usd":42000,"confidence":0.87,"urgency":"HIGH",
         "ai_reasoning":"Chicago at 78% with stable demand. Dallas at 91% CRITICAL. Transfer reduces Dallas risk from 18.7% to 4.2% stockout probability."},
        {"from_warehouse":"W004","to_warehouse":"W007","quantity":5200,"sku_category":"Components",
         "estimated_cost_usd":31000,"confidence":0.79,"urgency":"MEDIUM",
         "ai_reasoning":"Seattle Pacific underutilized at 55%. Singapore APAC at 88% warning. Rebalancing pre-empts Q4 APAC demand spike."},
    ]

@inventory_router.get("/alerts", summary="Get active inventory alerts")
async def get_inventory_alerts():
    return {
        "critical": [{"warehouse":"Dallas DC","alert":"Utilization 91% — stockout risk 18.7%","action_required":True}],
        "warning": [{"warehouse":"Singapore APAC","alert":"Utilization 88% — approaching threshold","action_required":False},
                    {"warehouse":"Frankfurt Euro","alert":"Electronics safety stock below 20%","action_required":False}],
        "total_alerts": 3,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

async def _run_rl_optimization(job_id: str, request: dict):
    """Background RL optimization task (production: Celery worker)."""
    logger.info(f"Running RL inventory optimization | job_id={job_id}")
    import asyncio; await asyncio.sleep(2)  # Simulate processing
    logger.info(f"RL optimization complete | job_id={job_id}")


# ═══════════════════════════════════════════════
# backend/api/routes/suppliers.py
# ═══════════════════════════════════════════════
suppliers_router = InventoryRouter()

class SupplierRiskResponse(BaseModel):
    supplier_id: str; name: str; country: str; region: str
    category: str; risk_level: str; risk_score: int
    on_time_delivery_rate: float; monthly_volume: int
    annual_spend_usd: int; tier: int
    key_risk_factors: List[str]
    recommended_actions: List[str]
    last_scored_at: str

@suppliers_router.get("/", summary="List all suppliers with risk scores")
async def list_suppliers(
    risk_level: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    sort_by: str = Query("risk_score", regex="^(risk_score|name|country|volume)$"),
):
    suppliers = _mock_suppliers()
    if risk_level:
        suppliers = [s for s in suppliers if s["risk_level"] == risk_level.upper()]
    if region:
        suppliers = [s for s in suppliers if s["region"] == region.upper()]
    reverse = sort_by == "risk_score"
    suppliers.sort(key=lambda x: x.get(sort_by, 0), reverse=False if sort_by != "risk_score" else True)
    return {"suppliers": suppliers, "total": len(suppliers), "generated_at": datetime.now(timezone.utc).isoformat()}

@suppliers_router.get("/{supplier_id}/risk", summary="Detailed supplier risk analysis")
async def get_supplier_risk(supplier_id: str):
    suppliers = _mock_suppliers()
    supplier = next((s for s in suppliers if s["id"] == supplier_id), None)
    if not supplier:
        raise HTTPException(status_code=404, detail=f"Supplier {supplier_id} not found")
    return {
        **supplier,
        "risk_history": [{"date": f"2024-11-{18-i:02d}", "score": supplier["risk_score"] + i*2} for i in range(14)],
        "dependency_graph": {"direct_products": 12, "sole_source_items": 4, "cascading_risk_items": 8},
        "alternative_suppliers": [
            {"id": "S006", "name": "Seoul Semiconductor", "risk_score": 93, "lead_time_delta_days": 5, "cost_delta_pct": 12},
        ],
    }

@suppliers_router.post("/{supplier_id}/risk/rescore", summary="Trigger risk rescoring")
async def rescore_supplier(supplier_id: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(logger.info, f"Rescoring supplier {supplier_id}")
    return {"supplier_id": supplier_id, "status": "RESCORING", "estimated_completion_seconds": 15}

def _mock_suppliers():
    return [
        {"id":"S001","name":"Shenzhen Electronics Co.","country":"China","region":"APAC","category":"Electronics",
         "risk_level":"CRITICAL","risk_score":32,"on_time_delivery_rate":0.61,"monthly_volume":45000,
         "annual_spend_usd":8_400_000,"tier":1,
         "key_risk_factors":["Factory closure confirmed — 60-day shutdown","Delivery rate fallen to 61% (was 89%)","Country geopolitical risk elevated"],
         "recommended_actions":["Immediately activate Seoul Semiconductor as primary","Increase safety stock 60% for Electronics","Escalate to CPO"],
         "last_scored_at": "2024-11-18T14:03:00Z"},
        {"id":"S006","name":"Seoul Semiconductor","country":"S. Korea","region":"APAC","category":"Semiconductors",
         "risk_level":"LOW","risk_score":93,"on_time_delivery_rate":0.97,"monthly_volume":38000,
         "annual_spend_usd":6_200_000,"tier":1,
         "key_risk_factors":[],"recommended_actions":["Increase order volume to offset Shenzhen gap"],
         "last_scored_at": "2024-11-18T14:03:00Z"},
        {"id":"S003","name":"Munich Industrial GmbH","country":"Germany","region":"EMEA","category":"Machinery",
         "risk_level":"LOW","risk_score":91,"on_time_delivery_rate":0.96,"monthly_volume":18000,
         "annual_spend_usd":4_100_000,"tier":1,
         "key_risk_factors":[],"recommended_actions":[],
         "last_scored_at": "2024-11-18T14:03:00Z"},
        {"id":"S005","name":"São Paulo Logistics SA","country":"Brazil","region":"LATAM","category":"Raw Materials",
         "risk_level":"HIGH","risk_score":44,"on_time_delivery_rate":0.74,"monthly_volume":15000,
         "annual_spend_usd":2_800_000,"tier":2,
         "key_risk_factors":["Payment delays averaging 22 days","Currency volatility — BRL depreciation 8% QTD","Port congestion at Santos"],
         "recommended_actions":["Place dual-source order with Mexico City Auto Parts","Request financial health certificate"],
         "last_scored_at": "2024-11-18T14:03:00Z"},
    ]


# ═══════════════════════════════════════════════
# backend/api/routes/kpis.py
# ═══════════════════════════════════════════════
kpis_router = InventoryRouter()
import random as _random

@kpis_router.get("/realtime", summary="Real-time operational KPI snapshot")
async def get_realtime_kpis():
    return {
        "otif": round(_random.uniform(85, 89.5), 1),
        "fill_rate": round(_random.uniform(93, 96), 1),
        "inventory_turnover": round(_random.uniform(7.1, 7.8), 1),
        "warehouse_utilization": round(_random.uniform(76, 82), 1),
        "transport_cost_per_unit": round(_random.uniform(2.3, 2.8), 2),
        "stockout_probability": round(_random.uniform(3.2, 5.1), 1),
        "supplier_reliability": round(_random.uniform(87, 92), 1),
        "delay_risk": round(_random.uniform(16, 22), 1),
        "ai_decisions_today": _random.randint(120, 210),
        "ai_auto_approve_rate": round(_random.uniform(91, 96), 1),
        "active_disruptions": 3,
        "pending_approvals": 2,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

@kpis_router.get("/trends", summary="KPI trend data — 24h, 7d, 30d")
async def get_kpi_trends(period: str = Query("24h", regex="^(24h|7d|30d|90d)$")):
    periods = {"24h": 24, "7d": 168, "30d": 720, "90d": 2160}
    n_points = min(periods[period], 100)  # Cap at 100 data points
    return {
        "period": period,
        "data_points": n_points,
        "otif": [round(_random.uniform(82, 93), 1) for _ in range(n_points)],
        "fill_rate": [round(_random.uniform(90, 97), 1) for _ in range(n_points)],
        "warehouse_utilization": [round(_random.uniform(72, 91), 1) for _ in range(n_points)],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

@kpis_router.get("/benchmarks", summary="KPI performance vs targets")
async def get_kpi_benchmarks():
    return {
        "kpis": [
            {"name": "OTIF", "current": 87.3, "target": 95.0, "threshold": 90.0, "status": "BELOW_THRESHOLD", "trend": "IMPROVING"},
            {"name": "Fill Rate", "current": 94.2, "target": 97.0, "threshold": 93.0, "status": "ABOVE_THRESHOLD", "trend": "STABLE"},
            {"name": "Inventory Turnover", "current": 7.4, "target": 8.0, "threshold": 6.0, "status": "ON_TRACK", "trend": "IMPROVING"},
            {"name": "WH Utilization", "current": 79.3, "target": 80.0, "threshold": 92.0, "status": "OPTIMAL", "trend": "STABLE"},
            {"name": "Supplier Reliability", "current": 89.1, "target": 92.0, "threshold": 85.0, "status": "ON_TRACK", "trend": "DECLINING"},
        ],
        "overall_health_score": 74,
        "ai_impact_score": 91,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════
# backend/api/routes/agents.py
# ═══════════════════════════════════════════════
agents_router = InventoryRouter()

class ApprovalRequest(BaseModel):
    approved: bool
    reason: Optional[str] = Field(None)
    approver_notes: Optional[str] = None

    class Config:
        @classmethod
        def model_validator(cls):
            # reason required for rejections
            pass

@agents_router.get("/status", summary="All agent health and activity status")
async def get_agent_status():
    return {"agents": [
        {"id":"AG1","name":"Planner Agent","status":"ACTIVE","decisions_today":47,"confidence_avg":0.94,
         "current_task":"Orchestrating Q4 demand surge response","last_decision_at":"2024-11-18T14:28:00Z"},
        {"id":"AG2","name":"Inventory Agent","status":"PROCESSING","decisions_today":31,"confidence_avg":0.87,
         "current_task":"Rebalancing Chicago→Dallas 8,400 units","last_decision_at":"2024-11-18T14:15:00Z"},
        {"id":"AG3","name":"Logistics Agent","status":"ACTIVE","decisions_today":28,"confidence_avg":0.91,
         "current_task":"Rerouting SH→LA via Singapore","last_decision_at":"2024-11-18T13:58:00Z"},
        {"id":"AG4","name":"Supplier Risk Agent","status":"ALERT","decisions_today":19,"confidence_avg":0.96,
         "current_task":"Escalating Shenzhen factory shutdown","last_decision_at":"2024-11-18T14:03:00Z"},
        {"id":"AG5","name":"Demand Forecasting","status":"ACTIVE","decisions_today":52,"confidence_avg":0.88,
         "current_task":"TFT model: Black Friday +340%","last_decision_at":"2024-11-18T14:09:00Z"},
        {"id":"AG6","name":"Escalation Agent","status":"IDLE","decisions_today":8,"confidence_avg":0.99,
         "current_task":"Monitoring approval queue (2 pending)","last_decision_at":"2024-11-18T13:45:00Z"},
        {"id":"AG7","name":"KPI Monitor Agent","status":"ACTIVE","decisions_today":63,"confidence_avg":1.00,
         "current_task":"OTIF at 87.3% — below 90% threshold","last_decision_at":"2024-11-18T14:21:00Z"},
        {"id":"AG8","name":"Executive Summary","status":"IDLE","decisions_today":12,"confidence_avg":0.97,
         "current_task":"Generating EOD intelligence brief","last_decision_at":"2024-11-18T12:00:00Z"},
    ], "summary": {"active": 5, "processing": 1, "idle": 2, "alert": 1, "total_decisions_today": 260,
                    "avg_confidence": 0.945, "auto_approve_rate": 0.941}}

@agents_router.get("/decisions", summary="Recent autonomous decisions")
async def get_decisions(
    status: Optional[str] = Query(None),
    agent_type: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
):
    decisions = [
        {"id":"DC001","agent":"Planner Agent","action":"Emergency PO issued: Seoul Semiconductor $2.4M",
         "confidence":0.94,"status":"AUTO_APPROVED","value_usd":2400000,
         "timestamp":"2024-11-18T14:28:00Z","reasoning":"Shenzhen closure creates 45K unit gap in Q4"},
        {"id":"DC002","agent":"Logistics Agent","action":"Reroute SH→LA via Singapore hub",
         "confidence":0.91,"status":"AUTO_APPROVED","value_usd":45000,
         "timestamp":"2024-11-18T13:58:00Z","reasoning":"Typhoon blocks direct SH-LA route. Singapore adds 2d but saves $45K vs air"},
        {"id":"DC003","agent":"Inventory Agent","action":"Chicago→Dallas transfer: 8,400 units",
         "confidence":0.87,"status":"PENDING","value_usd":420000,
         "timestamp":"2024-11-18T14:15:00Z","reasoning":"Dallas at 91% critical — transfer brings to 72% optimal range"},
        {"id":"DC004","agent":"Escalation Agent","action":"$8.7M alternative supplier contract",
         "confidence":0.72,"status":"HUMAN_REQUIRED","value_usd":8700000,
         "timestamp":"2024-11-18T13:45:00Z","reasoning":"Value exceeds $5M auto-approve threshold. Executive sign-off required."},
    ]
    if status:
        decisions = [d for d in decisions if d["status"] == status.upper()]
    return {"decisions": decisions[:limit], "total": len(decisions), "pending_human_approval": 2}

@agents_router.post("/decision/{decision_id}/approve", summary="Approve or reject a pending AI decision")
async def process_decision_approval(
    decision_id: str,
    approval: ApprovalRequest,
):
    if not approval.approved and not approval.reason:
        raise HTTPException(
            status_code=422,
            detail="A reason is required when rejecting a decision",
        )
    logger.info(f"Decision {decision_id} {'APPROVED' if approval.approved else 'REJECTED'} | reason={approval.reason}")
    action = "HUMAN_APPROVED" if approval.approved else "HUMAN_REJECTED"
    return {
        "decision_id": decision_id,
        "status": action,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "reason": approval.reason,
        "next_steps": "Decision execution queued" if approval.approved else "Decision archived. Alternative options will be generated.",
    }

@agents_router.get("/audit-trail", summary="Full immutable audit trail of all decisions")
async def get_audit_trail(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(50, le=500),
):
    return {
        "audit_entries": [
            {"timestamp":"2024-11-18T14:28:33Z","decision_id":"DC001","agent":"Planner Agent",
             "action":"AUTO_APPROVED","value_usd":2400000,"approver":"SYSTEM",
             "confidence":0.94,"outcome":"EXECUTED","impact":"Seoul PO confirmed — Q4 gap reduced 78%"},
            {"timestamp":"2024-11-18T13:45:11Z","decision_id":"DC004","agent":"Escalation Agent",
             "action":"ESCALATED_TO_HUMAN","value_usd":8700000,"approver":None,
             "confidence":0.72,"outcome":"PENDING","impact":"Awaiting executive approval"},
        ],
        "total_entries": 263,
        "auto_approved_count": 247,
        "human_approved_count": 11,
        "human_rejected_count": 5,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
