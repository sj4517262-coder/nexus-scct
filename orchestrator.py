"""
NEXUS Multi-Agent Orchestration Engine
LangGraph-based workflow for 8 specialized supply chain AI agents.
Agents communicate via structured JSON decisions, collaborate on
disruption response, and escalate to human operators when needed.
"""

import json
import logging
import os
import re
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
    alternatives_considered: List[str] = Field(default_factory=list)
    downstream_agents: List[AgentType] = Field(default_factory=list)
    requires_human_approval: bool = False
    auto_approve_threshold: float = 0.85
    metadata: Dict[str, Any] = Field(default_factory=dict)

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
    affected_entities: List[str] = Field(default_factory=list)
    estimated_impact_usd: Optional[float] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict)


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
        self.model_name = model_name
        self.api_key = (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN") or "").strip()
        self.llm = None

        # Anthropic is optional. With no key, NEXUS runs a deterministic local
        # decision engine so the full event -> agents -> approval pipeline works.
        if self.api_key:
            try:
                self.llm = ChatAnthropic(
                    model=model_name,
                    temperature=0.1,
                    api_key=self.api_key,
                )
                logger.info("NexusOrchestrator initialized with Anthropic model: %s", model_name)
            except Exception as exc:
                logger.warning("Anthropic initialization failed; using local agent mode: %s", exc)
        else:
            logger.info("No Anthropic API key configured; using local agent mode.")

        self.graph = self._build_graph()

    @staticmethod
    def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
        """Convert an arbitrary model value to float without crashing orchestration."""
        if value is None or value == "":
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_confidence(value: Any, default: float = 0.75) -> float:
        """Normalize LLM confidence to the valid [0, 1] range."""
        parsed = NexusOrchestrator._safe_float(value, default)
        if parsed is None:
            parsed = default
        return max(0.0, min(1.0, parsed))

    @staticmethod
    def _safe_severity(value: Any, default: SeverityLevel = SeverityLevel.MEDIUM) -> SeverityLevel:
        """Normalize LLM severity values, including lowercase/unknown values."""
        if isinstance(value, SeverityLevel):
            return value
        try:
            return SeverityLevel(str(value).strip().upper())
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _safe_agent_types(value: Any) -> List[AgentType]:
        """Normalize downstream agent names returned by the LLM."""
        if value is None:
            return []
        if isinstance(value, (str, AgentType)):
            value = [value]

        result: List[AgentType] = []
        if isinstance(value, list):
            for item in value:
                try:
                    result.append(
                        item if isinstance(item, AgentType)
                        else AgentType(str(item).strip().upper())
                    )
                except (ValueError, TypeError):
                    continue
        return result

    @staticmethod
    def _extract_json(raw: Any) -> Dict[str, Any]:
        """Extract a JSON object from a normal, fenced, or slightly wrapped LLM response."""
        if isinstance(raw, list):
            # Anthropic/LangChain may return content blocks.
            parts = []
            for block in raw:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(str(block.get("text", "")))
                elif hasattr(block, "text"):
                    parts.append(str(block.text))
                else:
                    parts.append(str(block))
            raw = "".join(parts)

        raw = str(raw or "").strip()

        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\\s*", "", raw, flags=re.IGNORECASE)
            raw = re.sub(r"\\s*```$", "", raw).strip()

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # Recover the first JSON object if the model added surrounding prose.
            match = re.search(r"\\{.*\\}", raw, flags=re.DOTALL)
            if not match:
                raise
            parsed = json.loads(match.group(0))

        if not isinstance(parsed, dict):
            raise ValueError("LLM response must be a JSON object")

        return parsed

    @staticmethod
    def _model_dump(model: BaseModel) -> Dict[str, Any]:
        """Support the Pydantic API used by this project."""
        if hasattr(model, "model_dump"):
            return model.model_dump()
        return model.dict()

    def _local_agent_decision(
        self,
        agent_type: AgentType,
        state: OrchestratorState,
    ) -> AgentDecision:
        """Deterministic local fallback used when no LLM API key is configured."""
        d = state["disruption"]
        severity = self._safe_severity(d.severity, SeverityLevel.MEDIUM)
        impact = self._safe_float(d.estimated_impact_usd, 0.0) or 0.0
        entities = ", ".join(d.affected_entities) or "affected entities"
        critical = severity in {SeverityLevel.HIGH, SeverityLevel.CRITICAL}

        if agent_type == AgentType.SUPPLIER_RISK:
            return AgentDecision(
                agent_type=agent_type,
                decision_type="SUPPLIER_RISK_ASSESSMENT",
                action=f"Assess supplier exposure for {entities} and activate alternate-supplier evaluation.",
                reasoning=f"{severity.value} {d.event_type} disruption requires supplier-risk mitigation.",
                confidence=0.91, estimated_value_usd=impact, risk_level=severity,
                requires_human_approval=critical,
                metadata={"risk_score": 82 if critical else 58, "mode": "local"},
            )
        if agent_type == AgentType.DEMAND_FORECAST:
            return AgentDecision(
                agent_type=agent_type, decision_type="DEMAND_IMPACT_ANALYSIS",
                action="Increase demand monitoring and review safety-stock targets for affected SKUs.",
                reasoning="Disruption signals can alter demand and service requirements.",
                confidence=0.88, estimated_value_usd=impact, risk_level=severity,
                requires_human_approval=critical,
                metadata={"demand_spike_probability": 0.35 if critical else 0.18, "mode": "local"},
            )
        if agent_type == AgentType.INVENTORY:
            return AgentDecision(
                agent_type=agent_type, decision_type="INVENTORY_REBALANCE",
                action="Evaluate emergency replenishment and inter-warehouse transfers for affected inventory.",
                reasoning=f"Protect inventory availability for {entities}.",
                confidence=0.90, estimated_value_usd=impact, risk_level=severity,
                requires_human_approval=critical, metadata={"mode": "local"},
            )
        if agent_type == AgentType.LOGISTICS:
            return AgentDecision(
                agent_type=agent_type, decision_type="ROUTE_CONTINGENCY",
                action="Evaluate alternate carriers and routes for exposed shipments.",
                reasoning="Routing contingencies reduce downstream delivery-delay exposure.",
                confidence=0.89, estimated_value_usd=impact, risk_level=severity,
                requires_human_approval=critical, metadata={"mode": "local"},
            )
        if agent_type == AgentType.KPI_MONITOR:
            return AgentDecision(
                agent_type=agent_type, decision_type="KPI_IMPACT_ASSESSMENT",
                action="Increase monitoring of OTIF, fill rate, utilization and transport cost.",
                reasoning="Operational KPIs provide early evidence of service degradation and recovery.",
                confidence=0.93, estimated_value_usd=impact, risk_level=severity,
                requires_human_approval=critical,
                metadata={"kpis": ["OTIF", "fill_rate", "warehouse_utilization", "transport_cost"], "mode": "local"},
            )
        if agent_type == AgentType.PLANNER:
            prior_value = sum(self._safe_float(x.estimated_value_usd, 0.0) or 0.0 for x in state["decisions"])
            total = max(impact, prior_value)
            return AgentDecision(
                agent_type=agent_type, decision_type="RESPONSE_PLAN",
                action="Coordinate supplier mitigation, inventory protection, logistics contingency and KPI monitoring.",
                reasoning=f"Synthesized {len(state['decisions'])} prior agent assessments.",
                confidence=0.92, estimated_value_usd=total, risk_level=severity,
                requires_human_approval=critical or total >= 1_000_000,
                alternatives_considered=["Alternate supplier", "Inventory rebalance", "Route contingency"],
                downstream_agents=[AgentType.ESCALATION, AgentType.EXECUTIVE_SUMMARY],
                metadata={"mode": "local"},
            )
        if agent_type == AgentType.ESCALATION:
            pending = any(x.status == DecisionStatus.PENDING_HUMAN for x in state["decisions"])
            required = critical or impact >= 1_000_000 or pending
            approver = "EXECUTIVE" if severity == SeverityLevel.CRITICAL or impact >= 5_000_000 else "MANAGER"
            return AgentDecision(
                agent_type=agent_type, decision_type="ESCALATION_ASSESSMENT",
                action=(f"Escalate to {approver} for human review." if required
                        else "Continue under automated operating policy with monitoring."),
                reasoning="Risk and value thresholds determine human oversight.",
                confidence=0.96, estimated_value_usd=impact, risk_level=severity,
                requires_human_approval=required,
                metadata={"approver_level": approver, "mode": "local"},
            )

        pending = sum(x.status == DecisionStatus.PENDING_HUMAN for x in state["decisions"])
        summary = (
            f"{severity.value} {d.event_type} disruption affecting {entities}. "
            f"Response coordinated across supplier, demand, inventory, logistics and KPI agents. "
            f"{pending} decision(s) require human review."
        )
        return AgentDecision(
            agent_type=agent_type, decision_type="EXECUTIVE_BRIEFING",
            action=summary, reasoning="Executive briefing synthesized from the completed workflow.",
            confidence=0.94, estimated_value_usd=impact, risk_level=severity,
            requires_human_approval=critical or pending > 0,
            metadata={"executive_summary": summary, "business_impact": impact, "mode": "local"},
        )

    def _call_agent(
        self,
        agent_type: AgentType,
        state: OrchestratorState,
        additional_context: str = "",
    ) -> AgentDecision:
        """Generic agent invocation with defensive structured-output handling."""
        disruption = state["disruption"]
        prior_decisions = state["decisions"]

        # estimated_impact_usd is optional in the event model. Never format None
        # with :,.0f because that raises TypeError and aborts the whole workflow.
        estimated_impact = self._safe_float(
            disruption.estimated_impact_usd,
            0.0,
        ) or 0.0

        context = f"""
DISRUPTION EVENT:
- Type: {disruption.event_type}
- Severity: {disruption.severity.value if isinstance(disruption.severity, SeverityLevel) else disruption.severity}
- Title: {disruption.title}
- Description: {disruption.description}
- Affected Entities: {', '.join(disruption.affected_entities)}
- Estimated Impact: ${estimated_impact:,.0f}

PRIOR AGENT DECISIONS:
{json.dumps([self._model_dump(d) for d in prior_decisions], indent=2, default=str)}

{additional_context}

Respond ONLY with valid JSON matching the requested decision structure.
"""

        messages = [
            SystemMessage(content=AGENT_PROMPTS[agent_type]),
            HumanMessage(content=context),
        ]

        try:
            if self.llm is None:
                decision = self._local_agent_decision(agent_type, state)
                if decision.should_auto_approve():
                    decision.status = DecisionStatus.AUTO_APPROVED
                else:
                    decision.status = DecisionStatus.PENDING_HUMAN
                logger.info(
                    "Agent %s decision: %s [conf=%.2f, status=%s, mode=local]",
                    agent_type.value, decision.action[:100],
                    decision.confidence, decision.status.value,
                )
                return decision

            response = self.llm.invoke(messages)
            raw_content = getattr(response, "content", response)
            data = self._extract_json(raw_content)

            # Keep agent-specific fields instead of silently discarding them.
            known_fields = {
                "decision_id",
                "agent_type",
                "timestamp",
                "decision_type",
                "action",
                "reasoning",
                "confidence",
                "estimated_value_usd",
                "risk_level",
                "status",
                "alternatives_considered",
                "downstream_agents",
                "requires_human_approval",
                "auto_approve_threshold",
                "metadata",
            }
            extra_metadata = {
                key: value for key, value in data.items()
                if key not in known_fields
            }

            supplied_metadata = data.get("metadata")
            if isinstance(supplied_metadata, dict):
                metadata = {**supplied_metadata, **extra_metadata}
            else:
                metadata = extra_metadata

            estimated_value = self._safe_float(data.get("estimated_value_usd"))

            decision = AgentDecision(
                agent_type=agent_type,
                decision_type=str(data.get("decision_type") or "ANALYSIS"),
                action=str(data.get("action") or "No action specified"),
                reasoning=str(data.get("reasoning") or ""),
                confidence=self._safe_confidence(data.get("confidence"), 0.75),
                estimated_value_usd=estimated_value,
                risk_level=self._safe_severity(
                    data.get("risk_level"),
                    SeverityLevel.MEDIUM,
                ),
                alternatives_considered=(
                    data.get("alternatives_considered")
                    if isinstance(data.get("alternatives_considered"), list)
                    else []
                ),
                downstream_agents=self._safe_agent_types(
                    data.get("downstream_agents")
                ),
                requires_human_approval=bool(
                    data.get("requires_human_approval", False)
                ),
                metadata=metadata,
            )

            if decision.should_auto_approve():
                decision.status = DecisionStatus.AUTO_APPROVED
            else:
                decision.status = DecisionStatus.PENDING_HUMAN

            logger.info(
                f"Agent {agent_type.value} decision: "
                f"{decision.action[:80]}... "
                f"[conf={decision.confidence:.2f}, status={decision.status.value}]"
            )
            return decision

        except Exception as e:
            logger.error(f"Agent {agent_type.value} failed: {e}", exc_info=True)
            return AgentDecision(
                agent_type=agent_type,
                decision_type="ERROR",
                action=f"Agent encountered an error: {str(e)[:100]}",
                reasoning="Agent processing failed — manual review required",
                confidence=0.0,
                status=DecisionStatus.FAILED,
                requires_human_approval=True,
                metadata={"error": str(e)},
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
        # Calculate total value at stake from all decisions, including the
        # planner's own recommendation.
        all_decisions = state["decisions"] + [decision]
        total_value = sum(
            (d.estimated_value_usd or 0.0)
            for d in all_decisions
        )
        return {
            **state,
            "decisions": all_decisions,
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
        # Preserve the event severity exactly; never silently downgrade CRITICAL.
        disruption.severity = self._safe_severity(disruption.severity, SeverityLevel.MEDIUM)

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
