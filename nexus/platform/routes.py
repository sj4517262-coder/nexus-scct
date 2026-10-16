"""Authenticated platform APIs used by the data, intelligence and operations screens."""
import json
from datetime import datetime,timezone
from fastapi import Depends,HTTPException,Query,Response
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select
from nexus.store import now,uid


class SimulationRequest(BaseModel):
    ticks:int=Field(default=1,ge=1,le=100)
    seed:int=Field(default=42,ge=0,le=1000000)


class PlanRequest(BaseModel):
    warehouse_id:str
    severity:str="MEDIUM"


class DocumentInput(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True)
    name:str=Field(min_length=3,max_length=120)
    text:str=Field(min_length=40,max_length=20000)


class ReroutePlan(BaseModel):
    shipment_id:str
    warehouse_id:str
    route:str=Field(min_length=3,max_length=200)
    eta:str
    reason:str=Field(min_length=5,max_length=1000)


def register(app,store,current_user,manager):
    @app.get("/api/v1/platform/status")
    def status(user=Depends(current_user)):
        from nexus.platform.models import summaries
        from nexus.platform.data import source_status
        from nexus.platform.intelligence import policy
        from nexus.platform.config import artifact_dir
        with store.transaction() as con:
            worker=store.get(con,"monitoring","worker")
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(worker["heartbeat"])).total_seconds() if worker else None
            counts={"outbox_pending":con.execute("SELECT COUNT(*) FROM outbox WHERE status='PENDING'").fetchone()[0],"outbox_published":con.execute("SELECT COUNT(*) FROM outbox WHERE status='PUBLISHED'").fetchone()[0],"events_processed":con.execute("SELECT COUNT(*) FROM inbox").fetchone()[0],"dead_letters":con.execute("SELECT COUNT(*) FROM dead_letters").fetchone()[0]}
            plans=sorted(store.all(con,"planning_runs"),key=lambda p:p["created_at"])[-20:]
            result=dict(storage="PostgreSQL" if store.path.startswith("postgresql") else "SQLite",worker={"status":"HEALTHY" if age is not None and age<30 else "STALE" if worker else "NOT_STARTED","age_seconds":round(age,1) if age else age},counts=counts,scenario=store.get(con,"meta","simulation"),purchase_orders=store.all(con,"purchase_orders"),planning_runs=plans,documents=store.all(con,"documents"),policy=policy(),drift=store.get(con,"monitoring","demand_drift"))
        result["models"]=summaries()
        result["sources"]=source_status()
        path=artifact_dir()/"m5_validation.json"
        result["m5_validation"]=json.loads(path.read_text()) if path.exists() else None
        result["monitoring"]=dict(requests=app.state.request_count,server_errors=app.state.error_count,request_seconds=round(app.state.request_seconds,2),planning_failures=sum(p["status"]=="FAILED" for p in plans),model_drift="Monitor simulated demand against the historical model; scenario-to-source domain shift is expected and explicitly labelled.")
        return result

    @app.post("/api/v1/platform/simulate",status_code=202)
    def simulate(body:SimulationRequest,user=Depends(manager)):
        from nexus.platform.simulator import simulate
        try:
            return simulate(body.ticks,body.seed,store)
        except (ValueError,FileNotFoundError) as exc:
            raise HTTPException(409,str(exc))

    @app.post("/api/v1/platform/plan")
    def plan(body:PlanRequest,user=Depends(manager)):
        from nexus.platform.intelligence import plan_replenishment
        try:
            with store.transaction() as con:
                return plan_replenishment(store,con,body.warehouse_id,trigger=user["email"],severity=body.severity)
        except (ValueError,FileNotFoundError) as exc:
            raise HTTPException(409,str(exc))

    @app.post("/api/v1/platform/execute/{identifier}")
    def execute(identifier:str,user=Depends(manager)):
        from nexus.platform.execution import execute_decision
        try:
            with store.transaction() as con:
                decision=store.get(con,"decisions",identifier)
                if decision and decision.get("policy",{}).get("required_role")=="EXECUTIVE" and user["role"] not in {"ADMIN","EXECUTIVE"}:
                    raise HTTPException(403,"Executive authorization required")
                return execute_decision(store,con,identifier,user["email"])
        except ValueError as exc:
            raise HTTPException(409,str(exc))

    @app.post("/api/v1/platform/reroute-plan")
    def reroute_plan(body:ReroutePlan,user=Depends(manager)):
        from datetime import date
        from nexus.platform.intelligence import evaluate_policy
        try:
            date.fromisoformat(body.eta)
        except ValueError:
            raise HTTPException(422,"ETA must be YYYY-MM-DD")
        with store.transaction() as con:
            shipment=store.get(con,"shipments",body.shipment_id)
            warehouse=store.get(con,"warehouses",body.warehouse_id)
            if not shipment or not warehouse or shipment.get("source")!="simulation" or warehouse.get("source")!="simulation" or shipment["status"]=="DELIVERED":
                raise HTTPException(409,"Choose an active simulation shipment and simulation warehouse")
            decision=dict(id=uid("DEC"),disruption_id=None,warehouse_id=warehouse["id"],agent="Logistics Agent",action_type="REROUTE",action=f"Reroute {shipment['tracking_number']} via {body.route}",reasoning=body.reason,confidence=.8,value_usd=0,status="PENDING",created_at=now(),reviewed_by=None,payload=body.model_dump(),policy=evaluate_policy(0,.8,.5,"HIGH","REROUTE"),source="simulation",severity="HIGH")
            store.put(con,"decisions",decision)
            store.event(con,"DECISION",decision["action"],user["email"],decision["id"])
            return decision

    @app.get("/api/v1/platform/forecasts")
    def forecasts(store_id:str|None=None,user=Depends(current_user)):
        from nexus.platform.models import demand_forecast,summaries
        try:
            return {"points":demand_forecast(store_id),"model":summaries()["demand"]}
        except ValueError as exc:
            raise HTTPException(409,str(exc))

    @app.get("/api/v1/platform/source-records/{source_id}")
    def records(source_id:str,limit:int=Query(50,ge=1,le=200),user=Depends(current_user)):
        from nexus.platform.config import engine
        from nexus.platform import schema
        table={"m5":schema.series,"dataco":schema.logistics,"sf_procurement":schema.procurement}.get(source_id)
        if table is None:
            raise HTTPException(404,"Unknown source")
        with engine().connect() as con:
            return [dict(row) for row in con.execute(select(table).limit(limit)).mappings()]

    @app.post("/api/v1/platform/documents",status_code=201)
    def add_document(body:DocumentInput,user=Depends(manager)):
        with store.transaction() as con:
            item=dict(id=uid("DOC"),name=body.name,text=body.text,created_at=now(),source="operator-supplied; untrusted context")
            store.put(con,"documents",item)
            store.event(con,"DOCUMENT",f"Knowledge document added: {body.name}",user["email"],item["id"])
            return item

    @app.get("/api/v1/platform/rag")
    def rag(q:str=Query(min_length=3,max_length=2000),user=Depends(current_user)):
        from nexus.platform.intelligence import retrieve
        with store.transaction() as con:
            matches=retrieve(q,store.all(con,"documents"))
        return {"answer":"\n\n".join(f"[{m['source']} §{m['chunk']}] {m['text']}" for m in matches) if matches else "No supporting policy passage found.","citations":matches,"generation":"Extractive, source-grounded retrieval; documents cannot alter execution policy"}

    @app.get("/api/v1/platform/dead-letters")
    def dead_letters(user=Depends(manager)):
        with store.transaction() as con:
            return [dict(r) for r in con.execute("SELECT * FROM dead_letters ORDER BY created_at DESC LIMIT 100").fetchall()]

    @app.post("/api/v1/platform/dead-letters/{identifier}/retry")
    def retry(identifier:str,user=Depends(manager)):
        with store.transaction() as con:
            row=con.execute("SELECT * FROM dead_letters WHERE id=?",(identifier,)).fetchone()
            if not row:
                raise HTTPException(404,"Dead letter not found")
            payload=json.loads(row["payload"])
            if payload.get("type") not in {"simulation.tick","decision.approved","execution.completed"}:
                raise HTTPException(409,"Unsupported event cannot be retried; correct the producer first")
            topic="nexus.execution" if payload["type"]=="decision.approved" else "nexus.simulation" if payload["type"]=="simulation.tick" else "nexus.state"
            event=store.enqueue(con,topic,payload)
            store.event(con,"RETRY","Dead-letter replay requested",user["email"],identifier,details={"new_event_id":event["event_id"]})
            return event

    @app.get("/metrics",include_in_schema=False)
    def prometheus():
        with store.transaction() as con:
            pending=con.execute("SELECT COUNT(*) FROM outbox WHERE status='PENDING'").fetchone()[0]
            failed=con.execute("SELECT COUNT(*) FROM dead_letters").fetchone()[0]
        metrics={"nexus_http_requests_total":app.state.request_count,"nexus_http_errors_total":app.state.error_count,"nexus_http_request_seconds_total":app.state.request_seconds,"nexus_outbox_pending":pending,"nexus_dead_letters":failed}
        return Response("\n".join(f"{key} {value}" for key,value in metrics.items())+"\n",media_type="text/plain; version=0.0.4")
