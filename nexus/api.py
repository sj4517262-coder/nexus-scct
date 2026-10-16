"""Local control tower API with durable transactions and authenticated workflows."""
import asyncio
import hashlib
import hmac
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool

from nexus.domain import AGENTS, forecast, metrics, orchestrate, recommendations, risk_level, warehouse_view
from nexus.store import Store, now, uid


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Credentials(Input):
    email: str = Field(min_length=5, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=10, max_length=128)


class SupplierInput(Input):
    name: str = Field(min_length=2, max_length=120)
    country: str = Field(min_length=2, max_length=80)
    category: str = Field(min_length=2, max_length=80)
    risk_score: int = Field(ge=0, le=100)
    monthly_volume: int = Field(ge=0, le=1000000000)
    lat: float = Field(default=0, ge=-90, le=90, allow_inf_nan=False)
    lng: float = Field(default=0, ge=-180, le=180, allow_inf_nan=False)


class WarehouseInput(Input):
    name: str = Field(min_length=2, max_length=120)
    capacity: int = Field(gt=0, le=1000000000)
    stock: int = Field(ge=0, le=1000000000)
    lat: float = Field(default=0, ge=-90, le=90, allow_inf_nan=False)
    lng: float = Field(default=0, ge=-180, le=180, allow_inf_nan=False)


class TransferInput(Input):
    from_warehouse: str
    to_warehouse: str
    quantity: int = Field(gt=0, le=1000000000)


class ShipmentInput(Input):
    tracking_number: str = Field(min_length=2, max_length=80)
    supplier_id: str
    warehouse_id: str
    carrier: str = Field(min_length=2, max_length=100)
    quantity: int = Field(gt=0, le=1000000000)
    cost_usd: float = Field(ge=0, le=1000000000, allow_inf_nan=False)
    eta: date


class RerouteInput(Input):
    warehouse_id: str
    route: str = Field(min_length=2, max_length=200)
    eta: date
    reason: str = Field(min_length=5, max_length=1000)


class DisruptionInput(Input):
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=10, max_length=2000)
    event_type: Literal["WEATHER", "GEOPOLITICAL", "SUPPLIER", "PORT", "DEMAND", "LOGISTICS"]
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    estimated_impact_usd: float = Field(default=0, ge=0, le=1000000000000, allow_inf_nan=False)
    affected_entities: list[str] = Field(default_factory=list, max_length=100)


class ReviewInput(Input):
    approved: bool
    reason: str = Field(min_length=5, max_length=1000)


class NotesInput(Input):
    notes: str = Field(min_length=5, max_length=1000)


class ChatInput(Input):
    message: str = Field(min_length=1, max_length=2000)


class DemandPoint(Input):
    date: date
    quantity: int = Field(ge=0, le=1000000000)

    @field_validator("date")
    @classmethod
    def historical_only(cls, value):
        if value >= date.today():
            raise ValueError("Demand observations must be dated before today")
        return value


class DemandInput(Input):
    observations: list[DemandPoint] = Field(min_length=14, max_length=3650)


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f"{salt}:{digest}"


def create_app(database_path=None):
    store = Store(database_path or os.getenv("NEXUS_DATABASE_URL") or os.getenv("NEXUS_DB_PATH", str(Path(__file__).resolve().parents[1]/"runtime"/"nexus.db")))
    origins = [x.strip() for x in os.getenv("NEXUS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000").split(",")]
    secure_cookie = os.getenv("NEXUS_SECURE_COOKIE", "false").lower() == "true"

    @asynccontextmanager
    async def lifespan(app):
        store.initialize()
        yield

    app = FastAPI(title="NEXUS Control Tower", version="4.0.0", lifespan=lifespan)
    app.state.store = store
    app.state.request_count = 0
    app.state.error_count = 0
    app.state.request_seconds = 0.0
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type"])

    @app.middleware("http")
    async def request_guard(request, call_next):
        from fastapi.responses import JSONResponse
        if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
            origin = request.headers.get("origin")
            if (origin and origin not in origins) or request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Untrusted request origin"}, status_code=403)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            app.state.error_count += 1
            raise
        else:
            app.state.error_count += int(response.status_code >= 500)
        finally:
            app.state.request_count += 1
            app.state.request_seconds += time.perf_counter() - started
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    def session_user(token):
        if not token:
            raise HTTPException(401, "Please sign in")
        with store.transaction() as con:
            row = con.execute("SELECT users.id,users.email,users.role FROM sessions JOIN users ON users.id=sessions.user_id WHERE token=? AND expires>?", (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        if not row:
            raise HTTPException(401, "Session expired. Please sign in again")
        return dict(row)

    def current_user(request: Request):
        return session_user(request.cookies.get("nexus_session"))

    def manager(user=Depends(current_user)):
        if user["role"] not in {"ADMIN", "MANAGER", "EXECUTIVE"}:
            raise HTTPException(403, "Manager role required")
        return user

    def require(con, kind, identifier):
        item = store.get(con, kind, identifier)
        if not item:
            raise HTTPException(404, f"{kind.rstrip('s').capitalize()} not found")
        return item

    def issue_session(con, user, response):
        token = secrets.token_urlsafe(32)
        con.execute("DELETE FROM sessions WHERE expires<=?", (time.time(),))
        con.execute("INSERT INTO sessions VALUES(?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user["id"], time.time()+43200))
        response.set_cookie("nexus_session", token, max_age=43200, httponly=True, secure=secure_cookie, samesite="strict", path="/")
        return {key: user[key] for key in ("id", "email", "role")}

    @app.get("/health")
    def health():
        with store.transaction() as con:
            con.execute("SELECT 1")
        return {"status": "healthy", "version": "4.0.0", "storage": "PostgreSQL" if store.path.startswith("postgresql") else "SQLite", "mode": "supply-chain simulation platform", "external_execution": False}

    @app.get("/api/v1/auth/status")
    def auth_status():
        with store.transaction() as con:
            return {"setup_required": con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0}

    @app.post("/api/v1/auth/setup", status_code=201)
    def setup(body: Credentials, response: Response):
        with store.transaction() as con:
            if con.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
                raise HTTPException(409, "Workspace already configured. Please sign in")
            user = dict(id=uid("USR"), email=body.email.lower(), role="ADMIN")
            con.execute("INSERT INTO users VALUES(?,?,?,?)", (user["id"], user["email"], password_hash(body.password), user["role"]))
            store.event(con, "AUTH", "Workspace owner created", user["email"])
            return issue_session(con, user, response)

    @app.post("/api/v1/auth/login")
    def login(body: Credentials, response: Response, request: Request):
        failure = False
        key = request.client.host if request.client else "local"
        with store.transaction() as con:
            attempt = con.execute("SELECT attempts,reset_at FROM login_attempts WHERE key=?", (key,)).fetchone()
            if attempt and attempt["reset_at"] > time.time() and attempt["attempts"] >= 10:
                raise HTTPException(429, "Too many sign-in attempts. Try again in 15 minutes")
            user = con.execute("SELECT * FROM users WHERE email=?", (body.email.lower(),)).fetchone()
            stored = user["password"] if user else password_hash("dummy-password")
            if not user or not hmac.compare_digest(password_hash(body.password, stored.split(":")[0]), stored):
                count = attempt["attempts"]+1 if attempt and attempt["reset_at"] > time.time() else 1
                reset = attempt["reset_at"] if attempt and attempt["reset_at"] > time.time() else time.time()+900
                con.execute("INSERT INTO login_attempts VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET attempts=excluded.attempts,reset_at=excluded.reset_at", (key,count,reset))
                failure = True
            else:
                con.execute("DELETE FROM login_attempts WHERE key=?", (key,))
                result = issue_session(con, user, response)
        if failure:
            raise HTTPException(401, "Incorrect email or password")
        return result

    @app.get("/api/v1/auth/me")
    def me(user=Depends(current_user)):
        return user

    @app.post("/api/v1/auth/logout")
    def logout(request: Request, response: Response):
        token = request.cookies.get("nexus_session", "")
        with store.transaction() as con:
            con.execute("DELETE FROM sessions WHERE token=?", (hashlib.sha256(token.encode()).hexdigest(),))
        response.delete_cookie("nexus_session", path="/")
        return {"ok": True}

    def snapshot_data():
        with store.transaction() as con:
            data = {k: store.all(con, k) for k in ("suppliers", "warehouses", "shipments", "disruptions", "decisions")}
            data["suppliers"] = [{**s, "risk_level": risk_level(s["risk_score"])} for s in data["suppliers"]]
            data["warehouses"] = [warehouse_view(w) for w in data["warehouses"]]
            runs = {r["id"]: r for r in store.all(con, "agent_runs")}
            data["agents"] = [dict(id=name, name=name, description=description, status="READY", **{"engine":"Rule-based", **{k:v for k,v in runs.get(name, {}).items() if k != "id"}}) for name,description in AGENTS]
            data["events"] = store.events(con)
            data["forecast"] = forecast(store.all(con, "demand"))
            data["recommendations"] = recommendations(data["warehouses"])
            data["kpis"] = metrics(data)
            data["generated_at"] = now()
            data["mode"] = "PostgreSQL platform · sample and simulation records" if store.path.startswith("postgresql") else "Local workspace · seeded sample data"
            return data

    @app.get("/api/v1/snapshot")
    def snapshot(user=Depends(current_user)):
        return snapshot_data()

    @app.get("/api/v1/suppliers")
    def suppliers(user=Depends(current_user)):
        return snapshot_data()["suppliers"]

    @app.get("/api/v1/inventory")
    def inventory(user=Depends(current_user)):
        return snapshot_data()["warehouses"]

    @app.get("/api/v1/shipments")
    def shipments(user=Depends(current_user)):
        return snapshot_data()["shipments"]

    @app.get("/api/v1/disruptions")
    def disruptions(user=Depends(current_user)):
        return snapshot_data()["disruptions"]

    @app.get("/api/v1/agents/decisions")
    def decisions(user=Depends(current_user)):
        return snapshot_data()["decisions"]

    @app.get("/api/v1/agents/status")
    def agents(user=Depends(current_user)):
        return snapshot_data()["agents"]

    @app.get("/api/v1/kpis/realtime")
    def kpis(user=Depends(current_user)):
        return snapshot_data()["kpis"]

    @app.get("/api/v1/inventory/rebalance-recommendations")
    def rebalance(user=Depends(current_user)):
        return snapshot_data()["recommendations"]

    @app.get("/api/v1/events")
    def events(after: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), user=Depends(current_user)):
        with store.transaction() as con:
            # Ascending replay prevents gaps when more than limit events are pending.
            rows = con.execute("SELECT seq,data FROM events WHERE seq>? ORDER BY seq LIMIT ?", (after,limit)).fetchall()
            import json
            return [{**json.loads(r["data"]), "seq": r["seq"]} for r in rows]

    @app.get("/api/v1/agents/audit-trail")
    def audit(limit: int = Query(500, ge=1, le=5000), user=Depends(current_user)):
        with store.transaction() as con:
            return store.events(con, limit=limit)

    @app.post("/api/v1/suppliers", status_code=201)
    def add_supplier(body: SupplierInput, user=Depends(manager)):
        with store.transaction() as con:
            item = store.put(con, "suppliers", {**body.model_dump(), "id": uid("SUP"), "updated_at": now()})
            store.event(con, "SUPPLIER", f"Supplier added: {body.name}", user["email"], item["id"])
            return item

    @app.patch("/api/v1/suppliers/{identifier}")
    def edit_supplier(identifier: str, body: SupplierInput, user=Depends(manager)):
        with store.transaction() as con:
            before = require(con, "suppliers", identifier)
            item = store.put(con, "suppliers", {**before, **body.model_dump(), "updated_at": now()})
            store.event(con, "RISK", f"Supplier updated: {body.name}", user["email"], identifier, risk_level(body.risk_score), {"before": before, "after": item})
            return item

    @app.post("/api/v1/inventory/warehouses", status_code=201)
    def add_warehouse(body: WarehouseInput, user=Depends(manager)):
        if body.stock > body.capacity:
            raise HTTPException(422, "Stock cannot exceed warehouse capacity")
        with store.transaction() as con:
            item = store.put(con, "warehouses", {**body.model_dump(), "id": uid("WH"), "updated_at": now()})
            store.event(con, "INVENTORY", f"Warehouse added: {body.name}", user["email"], item["id"])
            return item

    @app.post("/api/v1/inventory/transfer")
    def transfer(body: TransferInput, user=Depends(manager)):
        with store.transaction() as con:
            source = require(con, "warehouses", body.from_warehouse)
            dest = require(con, "warehouses", body.to_warehouse)
            if source["id"] == dest["id"]:
                raise HTTPException(422, "Choose two different warehouses")
            if body.quantity > source["stock"] or body.quantity+dest["stock"] > dest["capacity"]:
                raise HTTPException(409, "Insufficient source stock or destination capacity")
            source["stock"] -= body.quantity
            dest["stock"] += body.quantity
            for item in (source, dest):
                item["updated_at"] = now()
                store.put(con, "warehouses", item)
            store.event(con, "INVENTORY", f"Recorded transfer of {body.quantity:,} units: {source['name']} → {dest['name']}", user["email"], details=body.model_dump())
            return {"source": warehouse_view(source), "destination": warehouse_view(dest)}

    @app.post("/api/v1/shipments", status_code=201)
    def add_shipment(body: ShipmentInput, user=Depends(manager)):
        with store.transaction() as con:
            require(con, "suppliers", body.supplier_id)
            require(con, "warehouses", body.warehouse_id)
            if any(s["tracking_number"].casefold() == body.tracking_number.casefold() for s in store.all(con, "shipments")):
                raise HTTPException(409, "Tracking number already exists")
            item = store.put(con, "shipments", {**body.model_dump(mode="json"), "id": uid("SHP"), "status": "IN_TRANSIT", "delivered_at": None, "route": "Direct", "updated_at": now()})
            store.event(con, "SHIPMENT", f"Shipment created: {body.tracking_number}", user["email"], item["id"])
            return item

    @app.post("/api/v1/shipments/{identifier}/reroute")
    def reroute(identifier: str, body: RerouteInput, user=Depends(manager)):
        with store.transaction() as con:
            item = require(con, "shipments", identifier)
            if item.get("source") == "simulation":
                raise HTTPException(409, "Simulation shipment changes require an approved reroute plan")
            require(con, "warehouses", body.warehouse_id)
            if item["status"] == "DELIVERED":
                raise HTTPException(409, "Delivered shipments cannot be rerouted")
            before = dict(item)
            item.update(body.model_dump(mode="json"), status="REROUTED", updated_at=now())
            store.put(con, "shipments", item)
            store.event(con, "SHIPMENT", f"Rerouted {item['tracking_number']}: {body.route}", user["email"], identifier, details={"before": before, "after": item})
            return item

    @app.post("/api/v1/shipments/{identifier}/deliver")
    def deliver(identifier: str, user=Depends(manager)):
        with store.transaction() as con:
            item = require(con, "shipments", identifier)
            if item["status"] == "DELIVERED":
                raise HTTPException(409, "Shipment already delivered")
            warehouse = require(con, "warehouses", item["warehouse_id"])
            if warehouse["stock"]+item["quantity"] > warehouse["capacity"]:
                raise HTTPException(409, "Destination capacity exceeded; transfer stock or reroute first")
            warehouse["stock"] += item["quantity"]
            warehouse["updated_at"] = now()
            item.update(status="DELIVERED", delivered_at=now(), updated_at=now())
            store.put(con, "warehouses", warehouse)
            store.put(con, "shipments", item)
            store.event(con, "SHIPMENT", f"Received {item['quantity']:,} units from {item['tracking_number']} at {warehouse['name']}", user["email"], identifier)
            return item

    @app.post("/api/v1/disruptions", status_code=201)
    def add_disruption(body: DisruptionInput, user=Depends(manager)):
        with store.transaction() as con:
            known = {r["id"] for kind in ("suppliers", "warehouses", "shipments") for r in store.all(con, kind)}
            if any(identifier not in known for identifier in body.affected_entities):
                raise HTTPException(422, "Affected entity does not exist")
            item = store.put(con, "disruptions", {**body.model_dump(), "id": uid("DIS"), "status": "ACTIVE", "detected_at": now(), "resolved_at": None})
            store.event(con, "DISRUPTION", item["title"], user["email"], item["id"], item["severity"])
            decision = orchestrate(store, con, item, user["email"])
            return {"disruption": item, "decision": decision}

    @app.post("/api/v1/disruptions/{identifier}/analyze")
    def analyze(identifier: str, user=Depends(manager)):
        with store.transaction() as con:
            item = require(con, "disruptions", identifier)
            if item["status"] == "RESOLVED":
                raise HTTPException(409, "Disruption already resolved")
            pending = [d for d in store.all(con, "decisions") if d["disruption_id"] == identifier and d["status"] == "PENDING"]
            if pending:
                # Existing pending plan remains authoritative; populate reports without duplicating it.
                decision = pending[0]
                if not store.all(con, "agent_runs"):
                    for name, _ in AGENTS:
                        store.put(con, "agent_runs", dict(id=name, result="Pending plan already exists. Review the decision queue before requesting a new plan.", last_run=now(), disruption_id=identifier))
                return decision
            return orchestrate(store, con, item, user["email"])

    @app.patch("/api/v1/disruptions/{identifier}/resolve")
    def resolve(identifier: str, body: NotesInput, user=Depends(manager)):
        with store.transaction() as con:
            item = require(con, "disruptions", identifier)
            if item["status"] == "RESOLVED":
                raise HTTPException(409, "Disruption already resolved")
            item.update(status="RESOLVED", resolved_at=now(), resolution_notes=body.notes)
            store.put(con, "disruptions", item)
            for decision in store.all(con, "decisions"):
                if decision["disruption_id"] == identifier and decision["status"] == "PENDING":
                    decision.update(status="CANCELLED", reviewed_by=user["email"], reviewed_at=now(), review_reason="Associated disruption resolved")
                    store.put(con, "decisions", decision)
                    store.event(con, "DECISION", "Pending plan cancelled because disruption was resolved", user["email"], decision["id"])
            store.event(con, "DISRUPTION", f"Resolved: {item['title']}", user["email"], identifier, details={"notes": body.notes})
            return item

    @app.post("/api/v1/agents/decision/{identifier}/approve")
    def review(identifier: str, body: ReviewInput, user=Depends(manager)):
        with store.transaction() as con:
            item = require(con, "decisions", identifier)
            if item["status"] != "PENDING":
                raise HTTPException(409, "Decision already reviewed")
            if item.get("policy",{}).get("required_role") == "EXECUTIVE" and user["role"] not in {"ADMIN","EXECUTIVE"}:
                raise HTTPException(403, "Executive approval is required for this plan")
            item.update(status="APPROVED" if body.approved else "REJECTED", reviewed_by=user["email"], reviewed_at=now(), review_reason=body.reason)
            store.put(con, "decisions", item)
            store.event(con, "DECISION", f"Plan {item['status'].lower()}: {item['action']}", user["email"], identifier, details={"reason": body.reason, "external_execution": False})
            if body.approved and item.get("source") == "simulation" and item.get("action_type"):
                store.enqueue(con,"nexus.execution",dict(type="decision.approved",source="simulation",decision_id=identifier),identifier=f"approval:{identifier}")
            return item

    @app.get("/api/v1/forecast")
    def get_forecast(horizon: int = Query(28, ge=1, le=90), user=Depends(current_user)):
        with store.transaction() as con:
            return forecast(store.all(con, "demand"), horizon)

    @app.post("/api/v1/forecast/history")
    def import_demand(body: DemandInput, user=Depends(manager)):
        dates = [r.date for r in body.observations]
        if len(set(dates)) != len(dates):
            raise HTTPException(422, "Duplicate dates in demand history")
        if (max(dates)-min(dates)).days+1 != len(dates):
            raise HTTPException(422, "Provide consecutive daily observations, including zero-demand days")
        with store.transaction() as con:
            con.execute("DELETE FROM records WHERE kind='demand'")
            for row in body.observations:
                store.put(con, "demand", {**row.model_dump(mode="json"), "id": f"{row.date}:ALL", "source": "imported"})
            store.event(con, "FORECAST", f"Replaced demand history with {len(dates)} daily observations", user["email"])
            return forecast(store.all(con, "demand"))

    @app.post("/api/v1/copilot/chat")
    def chat(body: ChatInput, user=Depends(current_user)):
        data = snapshot_data()
        k = data["kpis"]
        q = body.message.lower()
        sources = ["Persisted operational records"]
        if any(word in q for word in ("policy", "policies", "document", "approval limit")):
            from nexus.platform.intelligence import retrieve
            with store.transaction() as con:
                citations=retrieve(body.message,store.all(con,"documents"))
            answer="\n\n".join(f"[{c['source']}] {c['text']}" for c in citations) or "No supporting passage found."
            sources=[f"{c['source']} section {c['chunk']}" for c in citations]
        elif any(word in q for word in ("supplier", "vendor", "risk")):
            risky = sorted(data["suppliers"], key=lambda s:s["risk_score"], reverse=True)[:3]
            answer = "Highest recorded supplier risk: "+"; ".join(f"{s['name']} ({s['risk_score']}/100, {s['risk_level'].lower()})" for s in risky)+". Higher scores mean higher risk; these scores are operator supplied."
        elif any(word in q for word in ("stock", "inventory", "warehouse")):
            answer = f"The workspace holds {k['total_stock']:,} units at {k['warehouse_utilization']}% capacity. {len(data['recommendations'])} transfers could reduce congestion. Review the Inventory page before recording a transfer."
        elif any(word in q for word in ("forecast", "demand")):
            from nexus.platform.models import summaries
            trained=summaries()["demand"]
            if trained:
                score=trained["test"]["candidate" if trained["selected_model"]=="gradient_boosting" else "baseline"]["wape"]
                answer=f"The trained M5 store-level forecast selected {trained['selected_model']} using validation WAPE. Its untouched test WAPE is {score:.2f}%. Historical observations end {trained['as_of']}; simulation explicitly projects these patterns forward. See Forecast lab for MAE, RMSE, baseline comparisons and per-store forecasts."
                sources=["M5 historical demand",f"MLflow run {trained['run_id']}"]
            else:
                answer = f"The local baseline projects {sum(p['forecast'] for p in data['forecast']['points']):,} units over 28 days from {data['forecast']['data_source']} history. Train the platform model for M5 evaluation results."
        elif any(word in q for word in ("approv", "decision", "agent")):
            answer = f"There are {k['pending_decisions']} plans awaiting review. LangGraph connects forecast and delay-risk models, policy retrieval and OR-Tools for simulation replenishment. Approving simulation plans queues simulated ERP execution, Kafka events and replanning. Sample narrative plans record reviews only. No real vendor is contacted."
        elif any(word in q for word in ("shipment", "delivery", "delay", "otif")):
            answer = f"There are {k['active_shipments']} active shipments and {k['delayed_shipments']} delayed or overdue. On-time delivery among delivered shipments is {k['on_time_delivery']}%. This is delivery timeliness, not an OTIF measure."
        else:
            answer = f"Workspace summary: {k['active_disruptions']} open disruptions, {k['pending_decisions']} pending plans, {k['active_shipments']} active shipments and {k['high_risk_suppliers']} high-risk suppliers. I can summarize suppliers, inventory, shipments, decisions and forecasts."
        return dict(answer=answer, sources=sources, generated_at=data["generated_at"], engine="Deterministic operational assistant")

    @app.websocket("/ws/events")
    async def websocket(websocket: WebSocket):
        if websocket.headers.get("origin") not in origins:
            await websocket.close(code=1008)
            return
        try:
            await run_in_threadpool(session_user, websocket.cookies.get("nexus_session"))
        except HTTPException:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        cursor = 0
        try:
            while True:
                await run_in_threadpool(session_user, websocket.cookies.get("nexus_session"))
                def read():
                    import json
                    with store.transaction() as con:
                        rows = con.execute("SELECT seq,data FROM events WHERE seq>? ORDER BY seq LIMIT 100", (cursor,)).fetchall()
                        return [{**json.loads(r["data"]), "seq":r["seq"]} for r in rows]
                batch = await run_in_threadpool(read)
                if batch:
                    cursor = batch[-1]["seq"]
                await websocket.send_json({"type": "events", "events": batch, "cursor": cursor})
                try:
                    await asyncio.wait_for(websocket.receive_text(), timeout=2)
                except asyncio.TimeoutError:
                    pass
        except (WebSocketDisconnect, RuntimeError):
            pass
        except HTTPException:
            await websocket.close(code=1008)

    from nexus.platform.routes import register
    register(app,store,current_user,manager)
    return app


app = create_app()
