"""
NEXUS AI Copilot API
Deterministic supply-chain reasoning layer that aggregates live NEXUS APIs.

This first version intentionally does not require an LLM API key.
It gathers live KPI, agent, decision, inventory, supplier, and disruption
context and produces grounded operational answers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field


router = APIRouter()


class CopilotRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class CopilotResponse(BaseModel):
    answer: str
    sources: List[str]
    context: Dict[str, Any]


async def _get_json(
    client: httpx.AsyncClient,
    path: str,
    default: Any,
) -> Any:
    try:
        response = await client.get(path)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return default


def _items(payload: Any, key: str | None = None) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if key and isinstance(payload, dict):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _status(value: Any) -> str:
    return str(value or "").upper()


def _agent_name(item: Dict[str, Any]) -> str:
    return str(
        item.get("name")
        or item.get("agent_name")
        or item.get("agent_type")
        or "NEXUS Agent"
    )


@router.post("/chat", response_model=CopilotResponse)
async def copilot_chat(request: CopilotRequest) -> CopilotResponse:
    """
    Answer operational supply-chain questions using live NEXUS backend data.
    """

    question = request.message.strip()
    q = question.lower()

    base_url = "http://127.0.0.1:8000"

    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=5.0,
    ) as client:
        kpis_task = _get_json(
            client,
            "/api/v1/kpis/realtime",
            {},
        )
        agents_task = _get_json(
            client,
            "/api/v1/agents/status",
            [],
        )
        decisions_task = _get_json(
            client,
            "/api/v1/agents/decisions?limit=20",
            [],
        )
        inventory_task = _get_json(
            client,
            "/api/v1/inventory/",
            [],
        )
        suppliers_task = _get_json(
            client,
            "/api/v1/suppliers/?sort_by=risk_score",
            [],
        )

        kpis, agents, decisions, inventory, suppliers = (
            await kpis_task,
            await agents_task,
            await decisions_task,
            await inventory_task,
            await suppliers_task,
        )

    agent_list = _items(agents, "agents")
    decision_list = _items(decisions, "decisions")
    inventory_list = _items(inventory)
    supplier_list = _items(suppliers)

    otif = _number(kpis.get("otif"))
    fill_rate = _number(kpis.get("fill_rate"))
    delay_risk = _number(kpis.get("delay_risk"))
    stockout_probability = _number(
        kpis.get("stockout_probability")
    )
    warehouse_utilization = _number(
        kpis.get("warehouse_utilization")
    )
    supplier_reliability = _number(
        kpis.get("supplier_reliability")
    )

    pending = [
        d
        for d in decision_list
        if _status(
            d.get("status") or d.get("decision_status")
        )
        in {
            "PENDING",
            "PENDING_HUMAN",
            "HUMAN_REQUIRED",
            "PROPOSED",
        }
    ]

    auto_approved = [
        d
        for d in decision_list
        if _status(
            d.get("status") or d.get("decision_status")
        )
        == "AUTO_APPROVED"
    ]

    risky_suppliers = sorted(
        supplier_list,
        key=lambda x: _number(
            x.get("risk_score"),
            _number(x.get("risk")),
        ),
        reverse=True,
    )

    critical_inventory = [
        item
        for item in inventory_list
        if _status(item.get("status"))
        in {"CRITICAL", "LOW", "STOCKOUT"}
        or _number(item.get("utilization")) >= 90
    ]

    active_agents = [
        a
        for a in agent_list
        if _status(
            a.get("status")
            or a.get("sts")
            or a.get("state")
        )
        in {"ACTIVE", "PROCESSING", "ALERT"}
    ]

    context = {
        "otif": otif,
        "fill_rate": fill_rate,
        "delay_risk": delay_risk,
        "stockout_probability": stockout_probability,
        "warehouse_utilization": warehouse_utilization,
        "supplier_reliability": supplier_reliability,
        "pending_decisions": len(pending),
        "auto_approved_decisions": len(auto_approved),
        "active_agents": len(active_agents),
        "total_agents": len(agent_list),
        "critical_inventory_items": len(critical_inventory),
        "high_risk_suppliers": len(risky_suppliers),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    sources = [
        "Live KPI API",
        "Live AI Agent Status API",
        "Live Agent Decision API",
    ]

    # ---------------------------------------------------------
    # QUESTION ROUTING
    # ---------------------------------------------------------

    if any(
        word in q
        for word in (
            "otif",
            "delivery",
            "fill rate",
            "performance",
            "kpi",
        )
    ):
        sources.append("Live operational KPI context")

        reasons = []

        if otif < 90:
            reasons.append(
                f"OTIF is {otif:.1f}%, below the 90% operational threshold"
            )

        if fill_rate < 95:
            reasons.append(
                f"fill rate is {fill_rate:.1f}%"
            )

        if delay_risk > 20:
            reasons.append(
                f"delay risk is elevated at {delay_risk:.1f}%"
            )

        if stockout_probability > 3:
            reasons.append(
                f"stockout probability is {stockout_probability:.1f}%"
            )

        if not reasons:
            reasons.append(
                "the monitored KPI values are currently within the configured operating thresholds"
            )

        answer = (
            f"Current OTIF is {otif:.1f}% and fill rate is "
            f"{fill_rate:.1f}%. "
            + "; ".join(reasons)
            + ". "
            f"There are {pending.__len__()} decisions awaiting review."
        )

    elif any(
        word in q
        for word in (
            "approval",
            "pending",
            "decision",
            "approve",
            "reject",
        )
    ):
        sources.append("Live human-approval decision queue")

        if pending:
            descriptions = []

            for decision in pending[:3]:
                action = (
                    decision.get("action")
                    or decision.get("decision_type")
                    or "Decision"
                )
                value = _number(
                    decision.get("estimated_value_usd")
                    or decision.get("value_usd")
                    or decision.get("value")
                )

                if value:
                    descriptions.append(
                        f"{action} (${value:,.0f})"
                    )
                else:
                    descriptions.append(str(action))

            answer = (
                f"There are {len(pending)} decisions currently "
                f"requiring review. "
                f"Examples: {'; '.join(descriptions)}."
            )
        else:
            answer = (
                "There are currently no pending human-approval "
                "decisions in the live decision queue."
            )

    elif any(
        word in q
        for word in (
            "supplier",
            "vendor",
            "supplier risk",
        )
    ):
        sources.append("Live supplier-risk API")

        if risky_suppliers:
            top = risky_suppliers[:3]
            details = []

            for supplier in top:
                name = (
                    supplier.get("supplier_name")
                    or supplier.get("name")
                    or supplier.get("supplier_id")
                    or "Supplier"
                )

                risk = _number(
                    supplier.get("risk_score")
                    or supplier.get("risk")
                )

                details.append(
                    f"{name} ({risk:.1f} risk)"
                )

            answer = (
                f"The highest supplier-risk records currently "
                f"returned by NEXUS are: "
                f"{'; '.join(details)}."
            )
        else:
            answer = (
                "No supplier-risk records were returned by "
                "the live supplier API."
            )

    elif any(
        word in q
        for word in (
            "inventory",
            "stock",
            "warehouse",
            "stockout",
        )
    ):
        sources.append("Live inventory API")

        if critical_inventory:
            details = []

            for item in critical_inventory[:3]:
                name = (
                    item.get("warehouse_name")
                    or item.get("warehouse_id")
                    or item.get("sku_id")
                    or "Inventory record"
                )

                status = (
                    item.get("status")
                    or "CRITICAL"
                )

                details.append(
                    f"{name}: {status}"
                )

            answer = (
                f"NEXUS currently has {len(critical_inventory)} "
                f"inventory records requiring attention. "
                f"Examples: {'; '.join(details)}."
            )
        else:
            answer = (
                "No inventory records currently meet the "
                "critical/low-stock conditions returned by the API."
            )

    elif any(
        word in q
        for word in (
            "agent",
            "agents",
            "ai status",
        )
    ):
        sources.append("Live agent-status API")

        names = [
            _agent_name(agent)
            for agent in active_agents[:8]
        ]

        answer = (
            f"{len(active_agents)} of {len(agent_list)} "
            f"agents are currently active, processing, or alerting. "
            f"Active operational agents include: "
            f"{', '.join(names) if names else 'none returned'}."
        )

    elif any(
        word in q
        for word in (
            "summary",
            "situation",
            "overview",
            "today",
            "status",
        )
    ):
        sources.extend(
            [
                "Live inventory API",
                "Live supplier-risk API",
            ]
        )

        answer = (
            f"NEXUS operational summary: OTIF is {otif:.1f}%, "
            f"fill rate is {fill_rate:.1f}%, delay risk is "
            f"{delay_risk:.1f}%, and stockout probability is "
            f"{stockout_probability:.1f}%. "
            f"{len(active_agents)} of {len(agent_list)} agents are "
            f"active/processing/alerting, with {len(pending)} "
            f"decisions awaiting human review. "
            f"{len(critical_inventory)} inventory records and "
            f"{len(risky_suppliers)} supplier records require "
            f"additional attention based on the current API data."
        )

    else:
        sources.extend(
            [
                "Live inventory API",
                "Live supplier-risk API",
            ]
        )

        answer = (
            f"I can analyze the current NEXUS supply-chain state. "
            f"Right now OTIF is {otif:.1f}%, fill rate is "
            f"{fill_rate:.1f}%, {len(pending)} decisions are "
            f"pending human review, and {len(active_agents)} "
            f"agents are active/processing/alerting. "
            f"Ask me about KPIs, inventory, suppliers, agents, "
            f"decisions, approvals, or the overall situation."
        )

    return CopilotResponse(
        answer=answer,
        sources=list(dict.fromkeys(sources)),
        context=context,
    )
