"""
NEXUS Multi-Agent Orchestration Engine
LangGraph-based workflow for 8 specialized supply chain AI agents.
Agents communicate via structured JSON decisions, collaborate on
disruption response, and escalate to human operators when needed.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

logger = logging.getLogger("nexus.orchestrator")


# ─────────────────────────────────────────────
# ENUMS & CONSTANTS
# ─────────────────────────────────────────────
class AgentType(str, Enum):
    PLANNER = "PLANNER"
    INVENTORY = "INVENTORY"
    LOGISTICS = "LOGISTICS"
    SUPPLIER_RISK = "SUPPLIER_RISK"
    DEMAND_FORECAST = "DEMAND_FORECAST"
    ESCALATION = "ESCALATION"
    KPI_MONITOR = "KPI_MONITOR"
    EXECUTIVE_SUMMARY = "EXECUTIVE_SUMMARY"


class DecisionStatus(str, Enum):
    PROPOSED = "PROPOSED"
    AUTO_APPROVED = "AUTO_APPROVED"
    PENDING_HUMAN = "PENDING_HUMAN"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    HUMAN_REJECTED = "HUMAN_REJECTED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


class SeverityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ─────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────
class AgentDecision(BaseModel):
    """Structured decision output from any agent."""
    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_type: AgentType
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    decision_type: str
    action: str
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)
    estimated_value_usd: Optional[float] = None
    risk_level: SeverityLevel = SeverityLevel.MEDIUM
    status: DecisionStatus = DecisionStatus.PROPOSED
    alternatives_considered: List[str] = []
    downstream_agents: List[AgentType] = []
    requires_human_approval: bool = False
    auto_approve_threshold: float = 0.85
    metadata: Dict[str, Any] = {}

    def should_auto_approve(self) -> bool:
        return (
            self.confidence >= self.auto_approve_threshold
            and not self.requires_human_approval
            and self.risk_level not in [SeverityLevel.CRITICAL]
            and (self.estimated_value_usd or 0) < 5_000_000
        )


class DisruptionEvent(BaseModel):
    """Incoming disruption event triggering orchestration."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str  # WEATHER, GEOPOLITICAL, SUPPLIER, PORT, DEMAND
    severity: SeverityLevel
    title: str
    description: str
    affected_entities: List[str] = []
    estimated_impact_usd: Optional[float] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = {}


class OrchestratorState(TypedDict):
    """LangGraph state shared across all agents."""
    disruption: DisruptionEvent
    decisions: List[AgentDecision]
    messages: List[Any]
    current_agent: str
    iteration: int
    completed_agents: List[str]
    final_plan: Optional[str]
    escalation_required: bool
    total_value_at_stake: float


# ─────────────────────────────────────────────
# AGENT SYSTEM PROMPTS
# ─────────────────────────────────────────────
AGENT_PROMPTS = {
    AgentType.PLANNER: """You are the Master Planner Agent for NEXUS, an enterprise supply chain AI platform.
Your role: Synthesize inputs from all agents, develop the optimal response strategy, and coordinate execution.
Always output a JSON decision with keys: decision_type, action, reasoning, confidence (0-1), estimated_value_usd, 
alternatives_considered (list of 3), downstream_agents, requires_human_approval.
Be decisive, data-driven, and consider cost, time, and risk tradeoffs.""",

    AgentType.INVENTORY: """You are the Inventory Optimization Agent for NEXUS.
Your role: Analyze warehouse stock levels, safety stock, reorder points, and recommend rebalancing actions.
Consider multi-echelon inventory theory, EOQ calculations, and demand variability.
Output JSON: decision_type, action (specific transfer quantities and locations), reasoning, confidence, estimated_value_usd.""",

    AgentType.LOGISTICS: """You are the Logistics & Route Optimization Agent for NEXUS.
Your role: Optimize shipment routes, select transportation modes, minimize cost and delay.
Apply VRP principles, consider port congestion, weather, and carrier capacity.
Output JSON with specific rerouting recommendations, ETA impacts, and cost comparisons.""",

    AgentType.SUPPLIER_RISK: """You are the Supplier Risk Intelligence Agent for NEXUS.
Your role: Score supplier risk (0-100), detect anomalies, recommend mitigation strategies.
Consider: financial stability, geopolitical exposure, delivery history, dependency concentration.
Output JSON with risk scores, affected SKUs, recommended alternative suppliers, and escalation urgency.""",

    AgentType.DEMAND_FORECAST: """You are the Demand Forecasting Agent for NEXUS.
Your role: Update demand forecasts based on disruption signals, seasonal patterns, and market data.
Use probabilistic forecasting — always include confidence intervals.
Output JSON with revised forecast, demand spike probability, SKU-level impacts, and recommended safety stock adjustments.""",

    AgentType.ESCALATION: """You are the Escalation Management Agent for NEXUS.
Your role: Evaluate which decisions require human approval based on value thresholds, risk levels, and policy.
Auto-approve decisions < $1M with confidence > 0.85. Escalate: decisions > $5M, CRITICAL severity, novel situations.
Output JSON with escalation decision, rationale, required approver level (MANAGER/EXECUTIVE/BOARD), and deadline.""",

    AgentType.KPI_MONITOR: """You are the KPI Monitoring Agent for NEXUS.
Your role: Track operational KPIs (OTIF, fill rate, WH utilization, transport cost), detect threshold breaches.
Generate alerts, identify root causes, and recommend corrective actions.
Output JSON with KPI impacts, breach details, root cause analysis, and recommended KPI recovery timeline.""",

    AgentType.EXECUTIVE_SUMMARY: """You are the Executive Summary Agent for NEXUS.
Your role: Synthesize all agent decisions into a concise C-suite briefing.
Structure: Situation → Impact → Response → Status → Decision Required.
Output JSON with executive_summary (3 sentences max), key_metrics, actions_taken, decisions_pending, business_impact.""",
}


# ─────────────────────────────────────────────
# AGENT NODES (LangGraph)
# ─────────────────────────────────────────────
class NexusOrchestrator:
    """
    Multi-agent orchestration engine using LangGraph.
    Coordinates 8 specialized agents in a directed acyclic workflow
    with conditional routing based on disruption severity.
    """

    def __init__(self, model_name: str = "claude-sonnet-4-20250514"):
        self.llm = ChatAnthropic(model=model_name, temperature=0.1)
        self.graph = self._build_graph()
        logger.info(f"NexusOrchestrator initialized with model: {model_name}")

    def _call_agent(
        self,
        agent_type: AgentType,
        state: OrchestratorState,
        additional_context: str = "",
    ) -> AgentDecision:
        """Generic agent invocation with structured output."""
        disruption = state["disruption"]
        prior_decisions = state["decisions"]

        context = f"""
DISRUPTION EVENT:
- Type: {disruption.event_type}
- Severity: {disruption.severity}
- Title: {disruption.title}
- Description: {disruption.description}
- Affected Entities: {', '.join(disruption.affected_entities)}
- Estimated Impact: ${disruption.estimated_impact_usd:,.0f}

PRIOR AGENT DECISIONS:
{json.dumps([d.dict() for d in prior_decisions], indent=2, default=str)}

{additional_context}

Respond ONLY with valid JSON matching the AgentDecision schema.
"""
        messages = [
            SystemMessage(content=AGENT_PROMPTS[agent_type]),
            HumanMessage(content=context),
        ]

        try:
            response = self.llm.invoke(messages)
            raw = response.content.strip()

            # Parse JSON response
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)

            decision = AgentDecision(
                agent_type=agent_type,
                decision_type=data.get("decision_type", "ANALYSIS"),
                action=data.get("action", "No action specified"),
                reasoning=data.get("reasoning", ""),
                confidence=float(data.get("confidence", 0.75)),
                estimated_value_usd=data.get("estimated_value_usd"),
                risk_level=SeverityLevel(data.get("risk_level", "MEDIUM")),
                alternatives_considered=data.get("alternatives_considered", []),
                downstream_agents=data.get("downstream_agents", []),
                requires_human_approval=data.get("requires_human_approval", False),
                metadata=data.get("metadata", {}),
            )

            # Auto-approve logic
            if decision.should_auto_approve():
                decision.status = DecisionStatus.AUTO_APPROVED
            else:
                decision.status = DecisionStatus.PENDING_HUMAN

            logger.info(
                f"Agent {agent_type} decision: {decision.action[:80]}... "
                f"[conf={decision.confidence:.2f}, status={decision.status}]"
            )
            return decision

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Agent {agent_type} failed: {e}")
            return AgentDecision(
                agent_type=agent_type,
                decision_type="ERROR",
                action=f"Agent encountered an error: {str(e)[:100]}",
                reasoning="Agent processing failed — manual review required",
                confidence=0.0,
                status=DecisionStatus.FAILED,
            )

    # ─── Agent Node Functions ──────────────────────
    def supplier_risk_node(self, state: OrchestratorState) -> OrchestratorState:
        """Supplier Risk Agent: First to run — identifies exposed suppliers."""
        logger.info("Running: Supplier Risk Agent")
        decision = self._call_agent(AgentType.SUPPLIER_RISK, state)
        return {
            **state,
            "decisions": state["decisions"] + [decision],
            "current_agent": "SUPPLIER_RISK",
            "completed_agents": state["completed_agents"] + ["SUPPLIER_RISK"],
        }

    def demand_forecast_node(self, state: OrchestratorState) -> OrchestratorState:
        """Demand Forecasting Agent: Updates demand model with disruption signal."""
        logger.info("Running: Demand Forecasting Agent")
        decision = self._call_agent(AgentType.DEMAND_FORECAST, state)
        return {
            **state,
            "decisions": state["decisions"] + [decision],
            "current_agent": "DEMAND_FORECAST",
            "completed_agents": state["completed_agents"] + ["DEMAND_FORECAST"],
        }

    def inventory_node(self, state: OrchestratorState) -> OrchestratorState:
        """Inventory Agent: Recommends stock adjustments based on risk + forecast."""
        logger.info("Running: Inventory Agent")
        decision = self._call_agent(AgentType.INVENTORY, state)
        return {
            **state,
            "decisions": state["decisions"] + [decision],
            "current_agent": "INVENTORY",
            "completed_agents": state["completed_agents"] + ["INVENTORY"],
        }

    def logistics_node(self, state: OrchestratorState) -> OrchestratorState:
        """Logistics Agent: Optimizes routes given disruption constraints."""
        logger.info("Running: Logistics Agent")
        decision = self._call_agent(AgentType.LOGISTICS, state)
        return {
            **state,
            "decisions": state["decisions"] + [decision],
            "current_agent": "LOGISTICS",
            "completed_agents": state["completed_agents"] + ["LOGISTICS"],
        }

    def kpi_monitor_node(self, state: OrchestratorState) -> OrchestratorState:
        """KPI Monitor: Assesses impact on OTIF, fill rate, cost metrics."""
        logger.info("Running: KPI Monitor Agent")
        decision = self._call_agent(AgentType.KPI_MONITOR, state)
        return {
            **state,
            "decisions": state["decisions"] + [decision],
            "current_agent": "KPI_MONITOR",
            "completed_agents": state["completed_agents"] + ["KPI_MONITOR"],
        }

    def planner_node(self, state: OrchestratorState) -> OrchestratorState:
        """Master Planner: Synthesizes all agent inputs into coherent response plan."""
        logger.info("Running: Planner Agent (synthesis)")
        decision = self._call_agent(
            AgentType.PLANNER,
            state,
            additional_context="You are synthesizing the final response strategy based on all agent analyses above.",
        )
        # Calculate total value at stake from all decisions
        total_value = sum(
            d.estimated_value_usd or 0
            for d in state["decisions"]
            if d.estimated_value_usd
        )
        return {
            **state,
            "decisions": state["decisions"] + [decision],
            "current_agent": "PLANNER",
            "completed_agents": state["completed_agents"] + ["PLANNER"],
            "total_value_at_stake": total_value,
        }

    def escalation_node(self, state: OrchestratorState) -> OrchestratorState:
        """Escalation Agent: Determines if human approval is needed."""
        logger.info("Running: Escalation Agent")
        decision = self._call_agent(AgentType.ESCALATION, state)

        pending_human = [
            d for d in state["decisions"]
            if d.status == DecisionStatus.PENDING_HUMAN
        ]
        escalation_required = (
            len(pending_human) > 0
            or state["disruption"].severity == SeverityLevel.CRITICAL
            or state["total_value_at_stake"] > 5_000_000
        )

        return {
            **state,
            "decisions": state["decisions"] + [decision],
            "current_agent": "ESCALATION",
            "completed_agents": state["completed_agents"] + ["ESCALATION"],
            "escalation_required": escalation_required,
        }

    def executive_summary_node(self, state: OrchestratorState) -> OrchestratorState:
        """Executive Summary Agent: Generates C-suite briefing."""
        logger.info("Running: Executive Summary Agent")
        decision = self._call_agent(AgentType.EXECUTIVE_SUMMARY, state)
        summary = decision.metadata.get("executive_summary", decision.action)
        return {
            **state,
            "decisions": state["decisions"] + [decision],
            "current_agent": "EXECUTIVE_SUMMARY",
            "completed_agents": state["completed_agents"] + ["EXECUTIVE_SUMMARY"],
            "final_plan": summary,
        }

    # ─── Conditional Routing ──────────────────────
    def route_after_planner(self, state: OrchestratorState) -> str:
        """Route to escalation, then executive summary."""
        return "escalation"

    def route_after_escalation(self, state: OrchestratorState) -> str:
        """Always generate executive summary."""
        return "executive_summary"

    # ─── Build LangGraph ──────────────────────────
    def _build_graph(self) -> StateGraph:
        """Build the multi-agent LangGraph workflow."""
        workflow = StateGraph(OrchestratorState)

        # Register all agent nodes
        workflow.add_node("supplier_risk", self.supplier_risk_node)
        workflow.add_node("demand_forecast", self.demand_forecast_node)
        workflow.add_node("inventory", self.inventory_node)
        workflow.add_node("logistics", self.logistics_node)
        workflow.add_node("kpi_monitor", self.kpi_monitor_node)
        workflow.add_node("planner", self.planner_node)
        workflow.add_node("escalation", self.escalation_node)
        workflow.add_node("executive_summary", self.executive_summary_node)

        # Define agent workflow DAG:
        # Supplier Risk + Demand Forecast (parallel) → Inventory + Logistics (parallel)
        # → KPI Monitor → Planner (synthesis) → Escalation → Executive Summary
        workflow.set_entry_point("supplier_risk")
        workflow.add_edge("supplier_risk", "demand_forecast")
        workflow.add_edge("demand_forecast", "inventory")
        workflow.add_edge("inventory", "logistics")
        workflow.add_edge("logistics", "kpi_monitor")
        workflow.add_edge("kpi_monitor", "planner")
        workflow.add_conditional_edges("planner", self.route_after_planner, {"escalation": "escalation"})
        workflow.add_conditional_edges("escalation", self.route_after_escalation, {"executive_summary": "executive_summary"})
        workflow.add_edge("executive_summary", END)

        return workflow.compile()

    # ─── Public Orchestration API ─────────────────
    async def handle_disruption(self, disruption: DisruptionEvent) -> Dict[str, Any]:
        """
        Main entry point: Orchestrate all agents in response to a disruption event.
        Returns the complete orchestration result with all decisions.
        """
        logger.info(
            f"Orchestration started | event_id={disruption.event_id} | "
            f"type={disruption.event_type} | severity={disruption.severity}"
        )

        initial_state: OrchestratorState = {
            "disruption": disruption,
            "decisions": [],
            "messages": [],
            "current_agent": "START",
            "iteration": 0,
            "completed_agents": [],
            "final_plan": None,
            "escalation_required": False,
            "total_value_at_stake": 0.0,
        }

        try:
            final_state = await self.graph.ainvoke(initial_state)

            result = {
                "orchestration_id": str(uuid.uuid4()),
                "event_id": disruption.event_id,
                "status": "COMPLETED",
                "agents_invoked": final_state["completed_agents"],
                "total_decisions": len(final_state["decisions"]),
                "auto_approved": sum(
                    1 for d in final_state["decisions"]
                    if d.status == DecisionStatus.AUTO_APPROVED
                ),
                "pending_human_approval": sum(
                    1 for d in final_state["decisions"]
                    if d.status == DecisionStatus.PENDING_HUMAN
                ),
                "escalation_required": final_state["escalation_required"],
                "total_value_at_stake_usd": final_state["total_value_at_stake"],
                "executive_summary": final_state["final_plan"],
                "decisions": [d.dict() for d in final_state["decisions"]],
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }

            logger.info(
                f"Orchestration completed | "
                f"decisions={result['total_decisions']} | "
                f"auto_approved={result['auto_approved']} | "
                f"escalation={result['escalation_required']}"
            )
            return result

        except Exception as e:
            logger.error(f"Orchestration failed: {e}", exc_info=True)
            return {
                "orchestration_id": str(uuid.uuid4()),
                "event_id": disruption.event_id,
                "status": "FAILED",
                "error": str(e),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }

    async def approve_decision(self, decision_id: str, approver: str, approved: bool) -> Dict:
        """Human approval/rejection of a pending decision."""
        logger.info(f"Decision {decision_id} {'APPROVED' if approved else 'REJECTED'} by {approver}")
        # In production: update decision in DB, trigger execution if approved
        return {
            "decision_id": decision_id,
            "status": DecisionStatus.HUMAN_APPROVED if approved else DecisionStatus.HUMAN_REJECTED,
            "approver": approver,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# ─────────────────────────────────────────────
# Singleton Instance
# ─────────────────────────────────────────────
_orchestrator: Optional[NexusOrchestrator] = None


def get_orchestrator() -> NexusOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = NexusOrchestrator()
    return _orchestrator
