from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from fastapi.testclient import TestClient
from nexus.api import create_app


def snapshot(client):
    response = client.get("/api/v1/snapshot")
    assert response.status_code == 200
    return response.json()


def disruption(client):
    response = client.post("/api/v1/disruptions", json={"title":"Factory outage detected", "description":"A production line has stopped after a power failure.", "event_type":"SUPPLIER", "severity":"CRITICAL", "estimated_impact_usd":2500000, "affected_entities":["S001"]})
    assert response.status_code == 201
    return response.json()


def test_auth_required_and_no_role_escalation(client):
    assert client.get("/api/v1/snapshot").status_code == 401
    assert client.post("/api/v1/inventory/transfer", json={"from_warehouse":"W001","to_warehouse":"W002","quantity":1}).status_code == 401
    assert client.post("/api/v1/auth/setup", json={"email":"a@example.com","password":"long-passphrase", "role":"ADMIN"}).status_code == 422


def test_simulation_reroute_cannot_bypass_review(owner):
    store=owner.app.state.store
    with store.transaction() as con:
        shipment=next(s for s in store.all(con,"shipments") if s["status"]!="DELIVERED")
        shipment["source"]="simulation"
        store.put(con,"shipments",shipment)
    response=owner.post(f"/api/v1/shipments/{shipment['id']}/reroute",json={"warehouse_id":"W001","route":"Alternate route","eta":"2030-01-01","reason":"Test approved-plan enforcement"})
    assert response.status_code==409
    assert "approved reroute plan" in response.json()["detail"]


def test_manager_cannot_approve_executive_plan(owner):
    store=owner.app.state.store
    with store.transaction() as con:
        decision=next(d for d in store.all(con,"decisions") if d["status"]=="PENDING")
        decision["policy"]={"required_role":"EXECUTIVE"}
        store.put(con,"decisions",decision)
        con.execute("UPDATE users SET role='MANAGER'")
    response=owner.post(f"/api/v1/agents/decision/{decision['id']}/approve",json={"approved":True,"reason":"Trying to exceed the manager approval limit"})
    assert response.status_code==403
    with store.transaction() as con:
        assert store.get(con,"decisions",decision["id"])["status"]=="PENDING"


def test_setup_login_logout_and_cookie_security(owner):
    assert owner.get("/api/v1/auth/status").json() == {"setup_required":False}
    assert owner.post("/api/v1/auth/setup", json={"email":"other@example.com","password":"long-passphrase"}).status_code == 409
    token = owner.cookies.get("nexus_session")
    assert owner.post("/api/v1/auth/logout").status_code == 200
    assert owner.get("/api/v1/auth/me", cookies={"nexus_session":token}).status_code == 401
    assert owner.post("/api/v1/auth/login", json={"email":"owner@example.com","password":"wrong-passphrase"}).status_code == 401
    response = owner.post("/api/v1/auth/login", json={"email":"OWNER@example.com","password":"test-passphrase-123"})
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]


def test_login_throttle(owner):
    owner.post("/api/v1/auth/logout")
    for _ in range(10):
        assert owner.post("/api/v1/auth/login", json={"email":"owner@example.com","password":"wrong-passphrase"}).status_code == 401
    assert owner.post("/api/v1/auth/login", json={"email":"owner@example.com","password":"test-passphrase-123"}).status_code == 429


def test_cross_origin_mutation_blocked(owner):
    response = owner.post("/api/v1/inventory/transfer", headers={"Origin":"https://untrusted.example"}, json={"from_warehouse":"W001","to_warehouse":"W002","quantity":1})
    assert response.status_code == 403


def test_operator_cannot_approve(owner, app):
    with app.state.store.transaction() as con:
        con.execute("UPDATE users SET role='OPERATOR'")
    assert owner.get("/api/v1/snapshot").status_code == 200
    assert owner.post("/api/v1/agents/decision/DEC-001/approve", json={"approved":True,"reason":"Reviewed carefully"}).status_code == 403


def test_kpis_stable_and_derived(owner):
    first = snapshot(owner)
    second = snapshot(owner)
    assert first["kpis"] == second["kpis"]
    assert first["kpis"]["on_time_delivery"] == 75
    assert first["kpis"]["total_stock"] == sum(w["stock"] for w in first["warehouses"])
    assert first["kpis"]["pending_decisions"] == 3


def test_atomic_transfer_and_capacity(owner):
    before = snapshot(owner)
    response = owner.post("/api/v1/inventory/transfer",json={"from_warehouse":"W002","to_warehouse":"W004","quantity":5000})
    assert response.status_code == 200
    assert response.json()["source"]["stock"] == 35950
    assert response.json()["destination"]["stock"] == 27000
    assert snapshot(owner)["kpis"]["total_stock"] == before["kpis"]["total_stock"]
    state = snapshot(owner)["warehouses"]
    for body, code in [({"from_warehouse":"W002","to_warehouse":"W002","quantity":10},422), ({"from_warehouse":"W001","to_warehouse":"W004","quantity":20000},409), ({"from_warehouse":"W001","to_warehouse":"W004","quantity":-1},422), ({"from_warehouse":"missing","to_warehouse":"W004","quantity":10},404)]:
        assert owner.post("/api/v1/inventory/transfer",json=body).status_code == code
    assert snapshot(owner)["warehouses"] == state


def test_recommendations_are_feasible(owner):
    data = snapshot(owner)
    for plan in data["recommendations"]:
        body = {key:plan[key] for key in ("from_warehouse","to_warehouse","quantity")}
        assert owner.post("/api/v1/inventory/transfer",json=body).status_code == 200
    after = snapshot(owner)
    assert after["kpis"]["total_stock"] == data["kpis"]["total_stock"]
    assert all(w["stock"] <= w["capacity"] for w in after["warehouses"])
    assert after["recommendations"] == []


def test_disruption_analysis_approval_and_conflicts(owner):
    item = disruption(owner)
    decision_id = item["decision"]["id"]
    data = snapshot(owner)
    assert all(a.get("last_run") for a in data["agents"])
    assert len(data["agents"]) == 8
    assert data["kpis"]["pending_decisions"] == 4
    assert owner.post(f"/api/v1/disruptions/{item['disruption']['id']}/analyze").json()["id"] == decision_id
    assert len(snapshot(owner)["decisions"]) == 4
    response = owner.post(f"/api/v1/agents/decision/{decision_id}/approve",json={"approved":True,"reason":"Alternate supply reviewed by operations"})
    assert response.status_code == 200
    assert response.json()["reviewed_by"] == "owner@example.com"
    assert owner.post(f"/api/v1/agents/decision/{decision_id}/approve",json={"approved":False,"reason":"Cannot reverse an existing review"}).status_code == 409
    assert snapshot(owner)["kpis"]["pending_decisions"] == 3
    assert any(e["entity_id"] == decision_id and e["details"].get("external_execution") is False for e in snapshot(owner)["events"])


def test_concurrent_reviews_only_one_wins(owner):
    def review(approved):
        return owner.post("/api/v1/agents/decision/DEC-001/approve",json={"approved":approved,"reason":"Concurrent review protection"}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(review,[True,False]))
    assert sorted(results) == [200,409]


def test_resolution_cancels_pending_decisions(owner):
    response = owner.patch("/api/v1/disruptions/DIS-001/resolve",json={"notes":"Carrier confirmed normal service has resumed"})
    assert response.status_code == 200
    data = snapshot(owner)
    assert next(d for d in data["decisions"] if d["id"] == "DEC-001")["status"] == "CANCELLED"
    assert owner.post("/api/v1/agents/decision/DEC-001/approve",json={"approved":True,"reason":"Already resolved"}).status_code == 409
    assert owner.patch("/api/v1/disruptions/missing/resolve",json={"notes":"Resolution notes"}).status_code == 404


def test_shipments_receipts_reroute_and_duplicate_protection(owner):
    body = dict(tracking_number="TEST-001",supplier_id="S001",warehouse_id="W004",carrier="Test carrier",quantity=100,cost_usd=200,eta=str(date.today()+timedelta(days=2)))
    response = owner.post("/api/v1/shipments",json=body)
    assert response.status_code == 201
    item = response.json()
    assert owner.post("/api/v1/shipments",json=body).status_code == 409
    assert owner.post("/api/v1/shipments",json={**body,"tracking_number":"OTHER","supplier_id":"missing"}).status_code == 404
    reroute = owner.post(f"/api/v1/shipments/{item['id']}/reroute",json={"warehouse_id":"W003","route":"Via Atlanta hub","eta":body["eta"],"reason":"Avoid congested west coast lane"})
    assert reroute.status_code == 200
    assert reroute.json()["status"] == "REROUTED"
    before = snapshot(owner)["kpis"]["total_stock"]
    assert owner.post(f"/api/v1/shipments/{item['id']}/deliver").status_code == 200
    assert snapshot(owner)["kpis"]["total_stock"] == before+100
    assert owner.post(f"/api/v1/shipments/{item['id']}/deliver").status_code == 409
    assert snapshot(owner)["kpis"]["total_stock"] == before+100
    assert owner.post(f"/api/v1/shipments/{item['id']}/reroute",json={"warehouse_id":"W004","route":"Direct","eta":body["eta"],"reason":"Cannot reroute received goods"}).status_code == 409


def test_receipt_over_capacity_rolls_back(owner):
    body=dict(tracking_number="TOO-MUCH",supplier_id="S001",warehouse_id="W002",carrier="Carrier",quantity=10000,cost_usd=100,eta=str(date.today()))
    item=owner.post("/api/v1/shipments",json=body).json()
    before=snapshot(owner)
    assert owner.post(f"/api/v1/shipments/{item['id']}/deliver").status_code == 409
    after=snapshot(owner)
    assert after["warehouses"] == before["warehouses"]
    assert after["shipments"] == before["shipments"]


def test_supplier_risk_direction_and_validation(owner):
    supplier=dict(name="New supplier",country="India",category="Components",risk_score=90,monthly_volume=1234,lat=12,lng=77)
    item=owner.post("/api/v1/suppliers",json=supplier)
    assert item.status_code == 201
    identifier=item.json()["id"]
    data=snapshot(owner)
    assert next(s for s in data["suppliers"] if s["id"] == identifier)["risk_level"] == "CRITICAL"
    assert owner.patch(f"/api/v1/suppliers/{identifier}",json={**supplier,"risk_score":10}).status_code == 200
    assert next(s for s in snapshot(owner)["suppliers"] if s["id"] == identifier)["risk_level"] == "LOW"
    assert owner.post("/api/v1/suppliers",json={**supplier,"risk_score":101}).status_code == 422


def test_forecast_horizon_ordering_and_import(owner):
    response=owner.get("/api/v1/forecast?horizon=90")
    assert response.status_code == 200
    assert len(response.json()["points"]) == 90
    assert all(0<=p["lower"]<=p["forecast"]<=p["upper"] for p in response.json()["points"])
    assert owner.get("/api/v1/forecast?horizon=91").status_code == 422
    observations=[dict(date=str(date.today()-timedelta(days=28-i)),quantity=500) for i in range(28)]
    result=owner.post("/api/v1/forecast/history",json={"observations":observations})
    assert result.status_code == 200
    assert all(p["forecast"] == 500 for p in result.json()["points"])
    assert result.json()["backtest_mape"] == 0
    assert result.json()["data_source"] == "imported / mixed"
    assert owner.post("/api/v1/forecast/history",json={"observations":observations+[observations[0]]}).status_code == 422
    assert owner.post("/api/v1/forecast/history",json={"observations":observations[1:5]+observations[6:]}).status_code == 422
    assert owner.post("/api/v1/forecast/history",json={"observations":[{**o,"date":str(date.today())} for o in observations]}).status_code == 422
    assert all(p["forecast"] == 500 for p in owner.get("/api/v1/forecast").json()["points"])


def test_copilot_uses_saved_data(owner):
    result=owner.post("/api/v1/copilot/chat",json={"message":"Which suppliers have the highest risk?"})
    assert result.status_code == 200
    assert "Shenzhen" in result.json()["answer"]
    assert "78/100" in result.json()["answer"]
    assert owner.post("/api/v1/copilot/chat",json={"message":"   "}).status_code == 422


def test_event_replay_paginates_without_gaps(owner):
    for i in range(6):
        owner.post("/api/v1/inventory/transfer",json={"from_warehouse":"W001","to_warehouse":"W004","quantity":1})
    cursor=0
    seen=[]
    while True:
        events=owner.get(f"/api/v1/events?after={cursor}&limit=2").json()
        if not events:
            break
        seen.extend(e["seq"] for e in events)
        cursor=events[-1]["seq"]
    assert seen == list(range(1,9))


def test_persistence_after_restart(owner, app):
    owner.post("/api/v1/agents/decision/DEC-001/approve",json={"approved":False,"reason":"Alternative is not feasible"})
    with TestClient(create_app(app.state.store.path)) as restarted:
        assert restarted.post("/api/v1/auth/login",json={"email":"owner@example.com","password":"test-passphrase-123"}).status_code == 200
        data=snapshot(restarted)
        assert len(data["suppliers"]) == 10
        assert next(d for d in data["decisions"] if d["id"] == "DEC-001")["status"] == "REJECTED"


def test_websocket_requires_auth_and_replays(owner, client):
    with owner.websocket_connect("/ws/events",headers={"origin":"http://localhost:3000"}) as ws:
        message=ws.receive_json()
        assert message["type"] == "events"
        assert len(message["events"]) == 2
        assert message["cursor"] == 2


def test_rest_collections_and_health(owner):
    assert owner.get("/health").json()["status"] == "healthy"
    for path in ("suppliers","shipments","disruptions","inventory","agents/decisions","agents/status","kpis/realtime","inventory/rebalance-recommendations"):
        assert owner.get(f"/api/v1/{path}").status_code == 200
