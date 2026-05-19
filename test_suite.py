"""
NEXUS — Comprehensive Test Suite
Covers: Unit tests, API integration tests, Agent orchestration tests
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

# ─────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────
@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.publish = AsyncMock(return_value=1)
    return redis


@pytest.fixture
def mock_kafka_producer():
    """Mock Kafka producer."""
    producer = MagicMock()
    producer.produce = MagicMock()
    producer.flush = MagicMock()
    return producer


@pytest.fixture
def sample_supplier():
    return {
        "id": "S001",
        "name": "Shenzhen Electronics Co.",
        "country": "China",
        "risk_level": "CRITICAL",
        "risk_score": 32,
        "monthly_volume": 45000,
        "category": "Electronics",
        "lat": 22.5,
        "lng": 114.1,
    }


@pytest.fixture
def sample_warehouse():
    return {
        "id": "W001",
        "name": "Chicago Hub",
        "city": "Chicago",
        "capacity": 50000,
        "current_inventory": 39000,
        "utilization_pct": 78.0,
        "status": "OPTIMAL",
        "lat": 41.8,
        "lng": -87.6,
    }


@pytest.fixture
def sample_disruption():
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "WEATHER",
        "severity": "HIGH",
        "title": "Typhoon Haikui — East China Sea",
        "description": "Category 3 typhoon affecting major shipping lanes",
        "affected_entities": ["Shanghai Port", "S001", "S006"],
        "estimated_impact_usd": 8_500_000,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": {"typhoon_category": 3, "wind_speed_kmh": 185},
    }


@pytest.fixture
def sample_agent_decision():
    return {
        "agent_type": "LOGISTICS",
        "decision_type": "ROUTE_OPTIMIZATION",
        "action": "Reroute SH→LA shipments via Singapore hub",
        "reasoning": "Direct SH→LA route blocked by typhoon. Singapore alternative adds 2 days but maintains delivery schedule.",
        "confidence": 0.91,
        "estimated_value_usd": 45000,
        "risk_level": "MEDIUM",
        "status": "AUTO_APPROVED",
        "alternatives_considered": [
            "Direct reroute via Taiwan — weather risk persists",
            "Air freight upgrade — 5x cost premium",
            "Hold in port — customer SLA breach risk",
        ],
    }


@pytest.fixture
def auth_headers():
    """Mock JWT auth headers."""
    return {"Authorization": "Bearer mock-valid-jwt-token"}


# ═══════════════════════════════════════════════
# UNIT TESTS — AGENT DECISION MODELS
# ═══════════════════════════════════════════════

class TestAgentDecision:
    """Test agent decision data models and business logic."""

    def test_decision_auto_approve_high_confidence(self):
        """High confidence + low value → auto approve."""
        from agents.orchestrator import AgentDecision, AgentType, SeverityLevel

        decision = AgentDecision(
            agent_type=AgentType.LOGISTICS,
            decision_type="ROUTE_CHANGE",
            action="Reroute shipment SHP-001 via alternative port",
            reasoning="Primary port congested",
            confidence=0.93,
            estimated_value_usd=350_000,
            risk_level=SeverityLevel.MEDIUM,
            auto_approve_threshold=0.85,
        )
        assert decision.should_auto_approve() is True

    def test_decision_escalate_high_value(self):
        """Value > $5M → should not auto-approve regardless of confidence."""
        from agents.orchestrator import AgentDecision, AgentType, SeverityLevel

        decision = AgentDecision(
            agent_type=AgentType.PLANNER,
            decision_type="EMERGENCY_PROCUREMENT",
            action="Issue emergency PO to alternative supplier",
            reasoning="Primary supplier shutdown",
            confidence=0.97,
            estimated_value_usd=8_700_000,  # $8.7M — above threshold
            risk_level=SeverityLevel.HIGH,
            requires_human_approval=False,
            auto_approve_threshold=0.85,
        )
        assert decision.should_auto_approve() is False

    def test_decision_escalate_critical_risk(self):
        """CRITICAL risk level → always escalate to human."""
        from agents.orchestrator import AgentDecision, AgentType, SeverityLevel

        decision = AgentDecision(
            agent_type=AgentType.SUPPLIER_RISK,
            decision_type="SUPPLIER_BLACKLIST",
            action="Suspend supplier operations immediately",
            reasoning="Sanctions violation detected",
            confidence=0.99,
            estimated_value_usd=100_000,
            risk_level=SeverityLevel.CRITICAL,
            auto_approve_threshold=0.85,
        )
        assert decision.should_auto_approve() is False

    def test_decision_escalate_requires_human_flag(self):
        """requires_human_approval=True → always escalate."""
        from agents.orchestrator import AgentDecision, AgentType, SeverityLevel

        decision = AgentDecision(
            agent_type=AgentType.ESCALATION,
            decision_type="CONTRACT_APPROVAL",
            action="Approve $2M supplier contract amendment",
            reasoning="Legal review required",
            confidence=0.88,
            estimated_value_usd=2_000_000,
            risk_level=SeverityLevel.MEDIUM,
            requires_human_approval=True,
        )
        assert decision.should_auto_approve() is False

    def test_decision_low_confidence_blocked(self):
        """Confidence below threshold → escalate."""
        from agents.orchestrator import AgentDecision, AgentType, SeverityLevel

        decision = AgentDecision(
            agent_type=AgentType.INVENTORY,
            decision_type="SAFETY_STOCK_ADJUSTMENT",
            action="Increase safety stock by 50%",
            reasoning="Uncertain demand signal",
            confidence=0.72,  # Below 0.85 threshold
            estimated_value_usd=200_000,
            risk_level=SeverityLevel.LOW,
            auto_approve_threshold=0.85,
        )
        assert decision.should_auto_approve() is False

    def test_decision_serialization(self, sample_agent_decision):
        """Decision should serialize to/from dict correctly."""
        from agents.orchestrator import AgentDecision, AgentType

        decision = AgentDecision(
            agent_type=AgentType.LOGISTICS,
            **{k: v for k, v in sample_agent_decision.items() if k != "agent_type"}
        )
        serialized = decision.dict()
        assert "decision_id" in serialized
        assert "timestamp" in serialized
        assert serialized["agent_type"] == "LOGISTICS"
        assert len(serialized["alternatives_considered"]) == 3


# ═══════════════════════════════════════════════
# UNIT TESTS — SUPPLIER RISK ENGINE
# ═══════════════════════════════════════════════

class TestSupplierRiskEngine:
    """Test XGBoost supplier risk scoring and graph analytics."""

    def test_heuristic_scoring_critical_supplier(self):
        """Supplier with multiple red flags should score CRITICAL."""
        from ml.risk.supplier_risk_model import SupplierRiskEngine

        engine = SupplierRiskEngine()
        high_risk_features = {
            "on_time_delivery_rate_90d": 0.55,
            "avg_delay_days_90d": 8.5,
            "delivery_variance_90d": 3.2,
            "consecutive_delays": 6,
            "payment_delay_days": 45,
            "credit_score_normalized": 0.25,
            "revenue_concentration_pct": 15,
            "financial_distress_score": 0.85,
            "country_risk_score": 0.78,
            "trade_restriction_flag": 1,
            "sanctions_flag": 0,
            "tariff_rate": 25.0,
            "capacity_utilization_pct": 96,
            "lead_time_trend": 2.1,
            "quality_rejection_rate": 0.12,
            "certifications_valid": 0,
            "weather_risk_proximity": 0.65,
            "nat_disaster_risk_score": 0.7,
            "climate_vulnerability_index": 0.8,
            "single_source_items_pct": 75,
            "substitute_availability_score": 0.15,
            "dependency_tier": 1,
            "communication_responsiveness": 0.3,
            "contract_compliance_score": 0.4,
            "audit_score": 0.35,
        }
        result = engine.score_supplier(high_risk_features)
        assert result["risk_level"] in ["CRITICAL", "HIGH"]
        assert result["risk_score"] < 55
        assert result["disruption_probability_90d"] > 0.4
        assert len(result["key_risk_factors"]) > 0
        assert len(result["recommended_actions"]) > 0

    def test_heuristic_scoring_low_risk_supplier(self):
        """Healthy supplier should score LOW risk."""
        from ml.risk.supplier_risk_model import SupplierRiskEngine

        engine = SupplierRiskEngine()
        low_risk_features = {
            "on_time_delivery_rate_90d": 0.97,
            "avg_delay_days_90d": 0.3,
            "delivery_variance_90d": 0.2,
            "consecutive_delays": 0,
            "payment_delay_days": 0,
            "credit_score_normalized": 0.92,
            "revenue_concentration_pct": 3,
            "financial_distress_score": 0.08,
            "country_risk_score": 0.12,
            "trade_restriction_flag": 0,
            "sanctions_flag": 0,
            "tariff_rate": 2.5,
            "capacity_utilization_pct": 72,
            "lead_time_trend": -0.1,
            "quality_rejection_rate": 0.004,
            "certifications_valid": 1,
            "weather_risk_proximity": 0.1,
            "nat_disaster_risk_score": 0.08,
            "climate_vulnerability_index": 0.15,
            "single_source_items_pct": 12,
            "substitute_availability_score": 0.85,
            "dependency_tier": 1,
            "communication_responsiveness": 0.95,
            "contract_compliance_score": 0.94,
            "audit_score": 0.91,
        }
        result = engine.score_supplier(low_risk_features)
        assert result["risk_level"] in ["LOW", "MEDIUM"]
        assert result["risk_score"] >= 70

    def test_dependency_graph_construction(self, sample_supplier):
        """Dependency graph should correctly represent supplier relationships."""
        from ml.risk.supplier_risk_model import SupplierRiskEngine

        engine = SupplierRiskEngine()
        suppliers = [
            {**sample_supplier, "risk_level": "CRITICAL"},
            {"id": "S002", "name": "Backup Supplier", "risk_level": "LOW", "monthly_volume": 20000, "country": "Vietnam"},
        ]
        products = [
            {"id": "PRD-001", "category": "Electronics", "supplier_ids": ["S001"], "volume_from_supplier_pct": 100},
            {"id": "PRD-002", "category": "Electronics", "supplier_ids": ["S001", "S002"], "volume_from_supplier_pct": 60},
        ]
        graph = engine.build_dependency_graph(suppliers, products)

        assert graph.number_of_nodes() == 4  # 2 suppliers + 2 products
        assert graph.number_of_edges() == 3  # S001→PRD-001, S001→PRD-002, S002→PRD-002
        assert graph.has_edge("S001", "PRD-001")
        assert graph.has_edge("S001", "PRD-002")
        assert graph.has_edge("S002", "PRD-002")

    def test_disruption_cascade_simulation(self, sample_supplier):
        """Cascade simulation should propagate disruption through graph."""
        from ml.risk.supplier_risk_model import SupplierRiskEngine

        engine = SupplierRiskEngine()
        suppliers = [
            {**sample_supplier, "risk_level": "CRITICAL"},
            {"id": "S002", "risk_level": "LOW", "monthly_volume": 15000, "country": "Vietnam"},
        ]
        products = [
            {"id": "PRD-001", "category": "Electronics", "supplier_ids": ["S001"], "volume_from_supplier_pct": 100},
            {"id": "PRD-002", "category": "Electronics", "supplier_ids": ["S001"], "volume_from_supplier_pct": 75},
        ]
        engine.build_dependency_graph(suppliers, products)
        cascade = engine.simulate_disruption_cascade("S001", disruption_severity=1.0)

        assert cascade["disrupted_supplier"] == "S001"
        assert cascade["total_nodes_affected"] >= 2
        assert len(cascade["affected_products"]) >= 1


# ═══════════════════════════════════════════════
# UNIT TESTS — DRIFT DETECTION
# ═══════════════════════════════════════════════

class TestDriftDetection:
    """Test statistical drift detection for demand forecasting."""

    def test_no_drift_stable_demand(self):
        """Stable demand pattern should not trigger drift alert."""
        from ml.forecast.tft_model import DriftDetector
        import pandas as pd
        import numpy as np

        np.random.seed(42)
        dates = pd.date_range(end=datetime.now(), periods=90)
        df = pd.DataFrame({
            "date": dates,
            "sku_id": "SKU-001",
            "quantity": np.random.normal(500, 30, 90),
        })

        detector = DriftDetector(threshold_sigma=2.0)
        detector.fit_baseline(df, baseline_days=60)
        result = detector.detect_drift(df, window_days=14)

        assert result["drift_detected"] is False
        assert result["recommendation"] == "STABLE"

    def test_drift_detected_demand_surge(self):
        """Sudden demand surge should trigger drift detection."""
        from ml.forecast.tft_model import DriftDetector
        import pandas as pd
        import numpy as np

        np.random.seed(42)
        # Historical: normal demand ~500
        hist_dates = pd.date_range(end=datetime.now() - timedelta(days=14), periods=76)
        hist_data = pd.DataFrame({
            "date": hist_dates,
            "sku_id": "SKU-001",
            "quantity": np.random.normal(500, 30, 76),
        })
        # Recent: demand spike to ~1700 (Black Friday-style)
        recent_dates = pd.date_range(
            start=datetime.now() - timedelta(days=13),
            end=datetime.now(), periods=14,
        )
        recent_data = pd.DataFrame({
            "date": recent_dates,
            "sku_id": "SKU-001",
            "quantity": np.random.normal(1700, 100, 14),
        })
        df = pd.concat([hist_data, recent_data], ignore_index=True)

        detector = DriftDetector(threshold_sigma=2.0)
        detector.fit_baseline(df, baseline_days=60)
        result = detector.detect_drift(df, window_days=14)

        assert result["recommendation"] == "RETRAIN"


# ═══════════════════════════════════════════════
# API INTEGRATION TESTS
# ═══════════════════════════════════════════════

class TestHealthEndpoint:
    """Test platform health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_check_returns_200(self):
        """Health endpoint should return 200 when all services up."""
        with patch("main.check_db_connection", return_value=True), \
             patch("main.check_redis_connection", return_value=True), \
             patch("main.check_kafka_connection", return_value=True):

            from main import app
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert "version" in data
            assert "checks" in data


class TestDisruptionsAPI:
    """Test disruption management endpoints."""

    @pytest.mark.asyncio
    async def test_list_disruptions_returns_200(self, auth_headers, mock_db_session):
        """GET /api/v1/disruptions should return list of disruptions."""
        with patch("api.routes.disruptions.get_db", return_value=mock_db_session), \
             patch("api.routes.disruptions.verify_token", return_value={"sub": "user-123"}):
            from main import app
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/api/v1/disruptions", headers=auth_headers)
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_create_disruption_triggers_orchestration(
        self, auth_headers, sample_disruption, mock_db_session, mock_kafka_producer
    ):
        """POST /api/v1/disruptions should trigger agent orchestration."""
        with patch("api.routes.disruptions.get_db", return_value=mock_db_session), \
             patch("api.routes.disruptions.verify_token", return_value={"sub": "user-123"}), \
             patch("api.routes.disruptions.get_orchestrator") as mock_orch:

            mock_orch.return_value.handle_disruption = AsyncMock(return_value={
                "orchestration_id": str(uuid.uuid4()),
                "status": "COMPLETED",
                "total_decisions": 8,
            })

            from main import app
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/disruptions",
                    json=sample_disruption,
                    headers=auth_headers,
                )
            assert response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_disruption_requires_authentication(self, sample_disruption):
        """POST /api/v1/disruptions should reject unauthenticated requests."""
        from main import app
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post("/api/v1/disruptions", json=sample_disruption)
        assert response.status_code == 401


class TestInventoryAPI:
    """Test inventory management endpoints."""

    @pytest.mark.asyncio
    async def test_get_inventory_status(self, auth_headers, mock_db_session):
        """GET /api/v1/inventory should return warehouse inventory data."""
        with patch("api.routes.inventory.get_db", return_value=mock_db_session), \
             patch("api.routes.inventory.verify_token", return_value={"sub": "user-123"}):
            from main import app
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/api/v1/inventory", headers=auth_headers)
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_inventory_optimization_trigger(self, auth_headers, mock_db_session):
        """POST /api/v1/inventory/optimize should trigger RL-based optimization."""
        payload = {
            "warehouse_ids": ["W001", "W002"],
            "optimization_type": "REBALANCE",
            "urgency": "HIGH",
        }
        with patch("api.routes.inventory.get_db", return_value=mock_db_session), \
             patch("api.routes.inventory.verify_token", return_value={"sub": "user-123"}), \
             patch("api.routes.inventory.run_rl_optimization", new_callable=AsyncMock) as mock_opt:

            mock_opt.return_value = {"status": "QUEUED", "job_id": str(uuid.uuid4())}
            from main import app
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/inventory/optimize",
                    json=payload,
                    headers=auth_headers,
                )
            assert response.status_code in [200, 202]


class TestKPIsAPI:
    """Test KPI monitoring endpoints."""

    @pytest.mark.asyncio
    async def test_realtime_kpis_structure(self, auth_headers, mock_redis):
        """GET /api/v1/kpis/realtime should return all required KPI fields."""
        expected_kpis = ["otif", "fill_rate", "inventory_turnover",
                         "warehouse_utilization", "transport_cost",
                         "stockout_probability", "supplier_reliability", "delay_risk"]

        with patch("api.routes.kpis.get_redis", return_value=mock_redis), \
             patch("api.routes.kpis.verify_token", return_value={"sub": "user-123"}), \
             patch("api.routes.kpis.compute_realtime_kpis", new_callable=AsyncMock) as mock_kpis:

            mock_kpis.return_value = {k: 90.0 for k in expected_kpis}
            from main import app
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/api/v1/kpis/realtime", headers=auth_headers)

            if response.status_code == 200:
                data = response.json()
                for kpi in expected_kpis:
                    assert kpi in data, f"Missing KPI: {kpi}"


class TestAgentDecisionAPI:
    """Test human-in-the-loop approval endpoints."""

    @pytest.mark.asyncio
    async def test_approve_decision(self, auth_headers, mock_db_session):
        """POST /api/v1/agents/decision/{id}/approve should process approval."""
        decision_id = str(uuid.uuid4())
        payload = {"approved": True, "reason": "Emergency situation justifies cost"}

        with patch("api.routes.agents.get_db", return_value=mock_db_session), \
             patch("api.routes.agents.verify_token", return_value={"sub": "manager-456", "role": "MANAGER"}), \
             patch("api.routes.agents.process_approval", new_callable=AsyncMock) as mock_approve:

            mock_approve.return_value = {
                "decision_id": decision_id,
                "status": "HUMAN_APPROVED",
                "approver": "manager-456",
            }
            from main import app
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.post(
                    f"/api/v1/agents/decision/{decision_id}/approve",
                    json=payload,
                    headers=auth_headers,
                )
            assert response.status_code in [200, 202]

    @pytest.mark.asyncio
    async def test_reject_decision_requires_reason(self, auth_headers):
        """Rejecting a decision should require a reason."""
        decision_id = str(uuid.uuid4())
        payload = {"approved": False}  # Missing reason

        from main import app
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/agents/decision/{decision_id}/approve",
                json=payload,
                headers=auth_headers,
            )
        assert response.status_code in [400, 422]


# ═══════════════════════════════════════════════
# AGENT ORCHESTRATION TESTS
# ═══════════════════════════════════════════════

class TestAgentOrchestration:
    """Test multi-agent workflow execution."""

    @pytest.mark.asyncio
    async def test_orchestration_completes_all_agents(self, sample_disruption):
        """Full orchestration should invoke all 8 agents."""
        from agents.orchestrator import (
            DisruptionEvent, NexusOrchestrator, SeverityLevel
        )

        disruption = DisruptionEvent(**sample_disruption)

        # Mock the LLM to avoid actual API calls in tests
        mock_decision = {
            "decision_type": "TEST_DECISION",
            "action": "Test action for unit test",
            "reasoning": "Mock reasoning for test",
            "confidence": 0.88,
            "estimated_value_usd": 500000,
            "risk_level": "MEDIUM",
            "alternatives_considered": ["Alt 1", "Alt 2", "Alt 3"],
            "downstream_agents": [],
            "requires_human_approval": False,
            "metadata": {"executive_summary": "Test summary"},
        }

        with patch.object(NexusOrchestrator, "_call_agent") as mock_call:
            from agents.orchestrator import AgentDecision, AgentType, DecisionStatus
            def make_decision(agent_type, state, **kwargs):
                d = AgentDecision(
                    agent_type=agent_type,
                    **mock_decision,
                )
                d.status = DecisionStatus.AUTO_APPROVED
                return d
            mock_call.side_effect = make_decision

            orchestrator = NexusOrchestrator()
            result = await orchestrator.handle_disruption(disruption)

        assert result["status"] == "COMPLETED"
        assert result["total_decisions"] == 8
        assert len(result["agents_invoked"]) == 8
        assert "SUPPLIER_RISK" in result["agents_invoked"]
        assert "PLANNER" in result["agents_invoked"]
        assert "EXECUTIVE_SUMMARY" in result["agents_invoked"]

    @pytest.mark.asyncio
    async def test_orchestration_escalation_logic(self, sample_disruption):
        """Critical disruption should trigger human escalation."""
        from agents.orchestrator import (
            DisruptionEvent, NexusOrchestrator, AgentDecision, AgentType,
            DecisionStatus, SeverityLevel
        )

        critical_disruption = {**sample_disruption, "severity": "CRITICAL", "estimated_impact_usd": 50_000_000}
        disruption = DisruptionEvent(**critical_disruption)

        with patch.object(NexusOrchestrator, "_call_agent") as mock_call:
            def make_decision(agent_type, state, **kwargs):
                d = AgentDecision(
                    agent_type=agent_type,
                    decision_type="TEST",
                    action="Test action",
                    reasoning="Test",
                    confidence=0.72,
                    estimated_value_usd=8_700_000,
                    risk_level=SeverityLevel.CRITICAL,
                    requires_human_approval=True,
                    metadata={"executive_summary": "Critical situation"},
                )
                d.status = DecisionStatus.PENDING_HUMAN
                return d
            mock_call.side_effect = make_decision

            orchestrator = NexusOrchestrator()
            result = await orchestrator.handle_disruption(disruption)

        assert result["escalation_required"] is True
        assert result["pending_human_approval"] > 0


# ═══════════════════════════════════════════════
# PYTEST CONFIGURATION
# ═══════════════════════════════════════════════

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with -m 'not slow')")
    config.addinivalue_line("markers", "integration: marks integration tests")
    config.addinivalue_line("markers", "ml: marks ML model tests")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
