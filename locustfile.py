"""
NEXUS — Enterprise Load Testing Suite
Locust-based performance testing simulating:
  - 500 concurrent operators and analysts
  - Real-time KPI dashboard polling
  - Agent decision workflows
  - WebSocket streaming connections
  - Disruption event processing

Usage:
  locust -f tests/load/locustfile.py --headless -u 500 -r 50 --run-time 10m
  locust -f tests/load/locustfile.py --host=http://localhost:8000
"""

import json
import random
import time
import uuid
from datetime import datetime

from locust import HttpUser, TaskSet, between, events, task
from locust.contrib.fasthttp import FastHttpUser


# ─────────────────────────────────────────────
# SHARED STATE & HELPERS
# ─────────────────────────────────────────────
DISRUPTION_TYPES = ["WEATHER", "GEOPOLITICAL", "SUPPLIER", "PORT", "DEMAND"]
SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
SUPPLIER_IDS = [f"SUP-{i:04d}" for i in range(1, 51)]
WAREHOUSE_IDS = [f"WH-{i:03d}" for i in range(1, 13)]
DECISION_STATUSES = ["AUTO_APPROVED", "PENDING", "HUMAN_REQUIRED"]


def get_auth_headers() -> dict:
    """Return mock JWT auth headers for test requests."""
    return {
        "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test-token",
        "Content-Type": "application/json",
        "X-Client-Version": "2.4.0",
    }


def random_disruption_payload() -> dict:
    """Generate a realistic disruption event payload."""
    return {
        "event_type": random.choice(DISRUPTION_TYPES),
        "severity": random.choice(SEVERITIES),
        "title": random.choice([
            "Typhoon affecting East China Sea shipping lanes",
            "Port worker strike — Rotterdam terminal",
            "Supplier factory shutdown — emergency protocol",
            "Geopolitical restriction on shipping routes",
            "Unexpected demand surge — electronics category",
        ]),
        "description": f"Automated load test disruption event {uuid.uuid4()}",
        "affected_entities": random.sample(SUPPLIER_IDS, k=random.randint(1, 4)),
        "estimated_impact_usd": random.randint(100_000, 50_000_000),
        "metadata": {
            "load_test": True,
            "test_id": str(uuid.uuid4()),
        },
    }


# ─────────────────────────────────────────────
# TASK SETS
# ─────────────────────────────────────────────
class DashboardTasks(TaskSet):
    """Simulate supply chain operator monitoring the dashboard."""

    @task(40)
    def poll_realtime_kpis(self):
        """Poll real-time KPIs — happens every ~10s in production UI."""
        with self.client.get(
            "/api/v1/kpis/realtime",
            headers=get_auth_headers(),
            name="GET /api/v1/kpis/realtime",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if "otif" not in data:
                    response.failure("Missing 'otif' in KPI response")
                elif response.elapsed.total_seconds() > 0.5:
                    response.failure(f"KPI response too slow: {response.elapsed.total_seconds():.3f}s")
                else:
                    response.success()
            else:
                response.failure(f"KPI request failed: {response.status_code}")

    @task(25)
    def get_active_disruptions(self):
        """Fetch active disruptions — refreshed every 30s."""
        with self.client.get(
            "/api/v1/disruptions",
            headers=get_auth_headers(),
            name="GET /api/v1/disruptions",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                if response.elapsed.total_seconds() > 0.8:
                    response.failure(f"Disruptions slow: {response.elapsed.total_seconds():.3f}s")
            else:
                response.failure(f"Failed: {response.status_code}")

    @task(20)
    def get_agent_status(self):
        """Check agent health — sidebar refreshes every 15s."""
        self.client.get(
            "/api/v1/agents/status",
            headers=get_auth_headers(),
            name="GET /api/v1/agents/status",
        )

    @task(10)
    def get_inventory_status(self):
        """Fetch warehouse inventory overview."""
        self.client.get(
            "/api/v1/inventory",
            headers=get_auth_headers(),
            name="GET /api/v1/inventory",
        )

    @task(5)
    def get_kpi_trends(self):
        """Load KPI trend charts — happens on page load."""
        period = random.choice(["24h", "7d", "30d"])
        self.client.get(
            f"/api/v1/kpis/trends?period={period}",
            headers=get_auth_headers(),
            name="GET /api/v1/kpis/trends",
        )


class SupplierRiskTasks(TaskSet):
    """Simulate supplier risk analyst workflows."""

    @task(35)
    def list_suppliers(self):
        """Fetch supplier list with risk scores."""
        risk_filter = random.choice(["", "?risk_level=HIGH", "?risk_level=CRITICAL", "?region=APAC"])
        self.client.get(
            f"/api/v1/suppliers/{risk_filter}",
            headers=get_auth_headers(),
            name="GET /api/v1/suppliers",
        )

    @task(30)
    def get_supplier_risk_detail(self):
        """Drill into specific supplier risk analysis."""
        supplier_id = random.choice(SUPPLIER_IDS)
        with self.client.get(
            f"/api/v1/suppliers/{supplier_id}/risk",
            headers=get_auth_headers(),
            name="GET /api/v1/suppliers/{id}/risk",
            catch_response=True,
        ) as response:
            if response.status_code not in [200, 404]:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(20)
    def trigger_rescore(self):
        """Trigger supplier risk rescoring."""
        supplier_id = random.choice(SUPPLIER_IDS)
        with self.client.post(
            f"/api/v1/suppliers/{supplier_id}/risk/rescore",
            headers=get_auth_headers(),
            name="POST /api/v1/suppliers/{id}/risk/rescore",
            catch_response=True,
        ) as response:
            if response.status_code not in [200, 202]:
                response.failure(f"Rescore failed: {response.status_code}")

    @task(15)
    def get_disruptions_filtered(self):
        """Fetch supplier-type disruptions only."""
        self.client.get(
            "/api/v1/disruptions?event_type=SUPPLIER",
            headers=get_auth_headers(),
            name="GET /api/v1/disruptions [filtered]",
        )


class AgentDecisionTasks(TaskSet):
    """Simulate operations manager handling AI decision workflows."""

    @task(30)
    def list_pending_decisions(self):
        """Poll for pending human-approval decisions."""
        with self.client.get(
            "/api/v1/agents/decisions?status=HUMAN_REQUIRED",
            headers=get_auth_headers(),
            name="GET /api/v1/agents/decisions [pending]",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if not isinstance(data, dict):
                    response.failure("Invalid response format")

    @task(25)
    def approve_decision(self):
        """Approve an AI-generated decision."""
        decision_id = str(uuid.uuid4())
        payload = {
            "approved": True,
            "reason": "Emergency situation validates cost — approved under $5M threshold",
            "approver_notes": f"Load test approval at {datetime.now().isoformat()}",
        }
        with self.client.post(
            f"/api/v1/agents/decision/{decision_id}/approve",
            json=payload,
            headers=get_auth_headers(),
            name="POST /api/v1/agents/decision/{id}/approve",
            catch_response=True,
        ) as response:
            if response.status_code not in [200, 202, 404]:
                response.failure(f"Approval failed: {response.status_code}")

    @task(20)
    def get_audit_trail(self):
        """Fetch decision audit trail."""
        self.client.get(
            "/api/v1/agents/audit-trail?limit=50",
            headers=get_auth_headers(),
            name="GET /api/v1/agents/audit-trail",
        )

    @task(15)
    def create_disruption(self):
        """Report a new disruption event (triggers orchestration)."""
        payload = random_disruption_payload()
        with self.client.post(
            "/api/v1/disruptions",
            json=payload,
            headers=get_auth_headers(),
            name="POST /api/v1/disruptions",
            catch_response=True,
        ) as response:
            if response.status_code not in [200, 201, 202]:
                response.failure(f"Disruption creation failed: {response.status_code}")
            elif response.elapsed.total_seconds() > 3.0:
                response.failure(f"Orchestration too slow: {response.elapsed.total_seconds():.2f}s")

    @task(10)
    def get_all_decisions(self):
        """Fetch complete decision history."""
        self.client.get(
            "/api/v1/agents/decisions?limit=20",
            headers=get_auth_headers(),
            name="GET /api/v1/agents/decisions",
        )


class InventoryTasks(TaskSet):
    """Simulate warehouse manager inventory workflows."""

    @task(35)
    def get_inventory_status(self):
        with self.client.get(
            "/api/v1/inventory",
            headers=get_auth_headers(),
            name="GET /api/v1/inventory",
        ):
            pass

    @task(25)
    def get_rebalance_recommendations(self):
        self.client.get(
            "/api/v1/inventory/rebalance-recommendations",
            headers=get_auth_headers(),
            name="GET /api/v1/inventory/rebalance-recommendations",
        )

    @task(25)
    def get_inventory_alerts(self):
        self.client.get(
            "/api/v1/inventory/alerts",
            headers=get_auth_headers(),
            name="GET /api/v1/inventory/alerts",
        )

    @task(15)
    def trigger_optimization(self):
        payload = {
            "warehouse_ids": random.sample(WAREHOUSE_IDS, k=random.randint(2, 4)),
            "optimization_type": random.choice(["REBALANCE", "SAFETY_STOCK", "EOQ"]),
            "urgency": random.choice(["LOW", "NORMAL", "HIGH", "CRITICAL"]),
        }
        with self.client.post(
            "/api/v1/inventory/optimize",
            json=payload,
            headers=get_auth_headers(),
            name="POST /api/v1/inventory/optimize",
            catch_response=True,
        ) as response:
            if response.status_code not in [200, 202]:
                response.failure(f"Optimization trigger failed: {response.status_code}")


# ─────────────────────────────────────────────
# USER CLASSES
# ─────────────────────────────────────────────
class DashboardOperator(FastHttpUser):
    """Primary user: operations manager monitoring dashboard. ~50% of load."""
    weight = 50
    wait_time = between(1, 5)
    tasks = [DashboardTasks]

    def on_start(self):
        """Authenticate on start."""
        self.client.get("/health")


class SupplierAnalyst(FastHttpUser):
    """Supplier risk analyst reviewing and scoring suppliers. ~20% of load."""
    weight = 20
    wait_time = between(2, 8)
    tasks = [SupplierRiskTasks]


class OperationsManager(FastHttpUser):
    """Operations manager handling AI decisions and approvals. ~20% of load."""
    weight = 20
    wait_time = between(3, 12)
    tasks = [AgentDecisionTasks]


class WarehouseManager(FastHttpUser):
    """Warehouse manager reviewing inventory and optimization. ~10% of load."""
    weight = 10
    wait_time = between(2, 10)
    tasks = [InventoryTasks]


# ─────────────────────────────────────────────
# PERFORMANCE THRESHOLDS (SLOs)
# ─────────────────────────────────────────────
SLO = {
    "GET /api/v1/kpis/realtime":     {"p95_ms": 200,  "p99_ms": 500,  "error_rate": 0.01},
    "GET /api/v1/disruptions":       {"p95_ms": 300,  "p99_ms": 800,  "error_rate": 0.01},
    "GET /api/v1/agents/status":     {"p95_ms": 250,  "p99_ms": 600,  "error_rate": 0.01},
    "GET /api/v1/inventory":         {"p95_ms": 300,  "p99_ms": 700,  "error_rate": 0.01},
    "POST /api/v1/disruptions":      {"p95_ms": 3000, "p99_ms": 8000, "error_rate": 0.05},
    "GET /api/v1/suppliers":         {"p95_ms": 400,  "p99_ms": 1000, "error_rate": 0.01},
}


@events.quitting.add_listener
def check_slos(environment, **kwargs):
    """Validate SLOs on test completion."""
    print("\n" + "="*60)
    print("SLO VALIDATION REPORT")
    print("="*60)

    failures = []
    stats = environment.stats

    for endpoint, thresholds in SLO.items():
        entry = stats.entries.get((endpoint, "GET")) or stats.entries.get((endpoint, "POST"))
        if not entry:
            continue

        p95 = entry.get_response_time_percentile(0.95)
        p99 = entry.get_response_time_percentile(0.99)
        err = entry.fail_ratio

        p95_ok = p95 <= thresholds["p95_ms"]
        p99_ok = p99 <= thresholds["p99_ms"]
        err_ok = err <= thresholds["error_rate"]

        status = "✅" if (p95_ok and p99_ok and err_ok) else "❌"
        print(f"{status} {endpoint}")
        print(f"   P95: {p95:.0f}ms (SLO: {thresholds['p95_ms']}ms) {'✓' if p95_ok else '✗'}")
        print(f"   P99: {p99:.0f}ms (SLO: {thresholds['p99_ms']}ms) {'✓' if p99_ok else '✗'}")
        print(f"   Err: {err:.2%} (SLO: {thresholds['error_rate']:.2%}) {'✓' if err_ok else '✗'}")

        if not (p95_ok and p99_ok and err_ok):
            failures.append(endpoint)

    print("="*60)
    if failures:
        print(f"❌ SLO VIOLATIONS: {len(failures)} endpoints breached thresholds")
        for f in failures:
            print(f"   - {f}")
        environment.process_exit_code = 1
    else:
        print("✅ ALL SLOs PASSED — Platform meets enterprise performance targets")
    print("="*60)
