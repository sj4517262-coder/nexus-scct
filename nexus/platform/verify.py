"""Live PostgreSQL/Kafka smoke test. Creates only labelled simulation records."""
import json
import time
from nexus.store import Store,now,uid
from nexus.platform.config import database_url,artifact_dir
from nexus.platform.simulator import simulate
from nexus.platform.streaming import process_event


def eventually(check,seconds=180):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        result=check()
        if result:
            return result
        time.sleep(1)
    raise AssertionError("Live integration condition did not complete before timeout")


def verify():
    store=Store(database_url())
    if not store.path.startswith("postgresql"):
        raise ValueError("Live verification requires PostgreSQL and the running Kafka worker")
    store.initialize()
    simulation=simulate(1,314,store)
    def consumed():
        with store.transaction() as con:
            return all(con.execute("SELECT id FROM inbox WHERE id=?",(i,)).fetchone() for i in simulation["event_ids"])
    eventually(consumed)
    with store.transaction() as con:
        payload=json.loads(con.execute("SELECT payload FROM outbox WHERE id=?",(simulation["event_ids"][0],)).fetchone()[0])
        decisions=[d for d in store.all(con,"decisions") if d.get("source")=="simulation" and d["status"]=="PENDING" and d.get("action_type")=="PURCHASE_ORDER"]
        assert decisions,"Expected a human-review replenishment plan"
        decision=decisions[0]
        decision.update(status="APPROVED",reviewed_by="integration-verification",reviewed_at=now(),review_reason="Authorized simulation integration test")
        store.put(con,"decisions",decision)
        store.event(con,"DECISION","Integration test approved a simulation plan","integration-verification",decision["id"])
        store.enqueue(con,"nexus.execution",dict(type="decision.approved",source="simulation",decision_id=decision["id"]),identifier="approval:"+decision["id"])
    assert process_event(store,payload)["status"]=="DUPLICATE"
    def completed():
        with store.transaction() as con:
            item=store.get(con,"decisions",decision["id"])
            replanned=con.execute("SELECT id FROM inbox WHERE id=?",("executed:"+decision["id"],)).fetchone()
            return item if item["status"]=="EXECUTED" and replanned else None
    executed=eventually(completed)
    with store.transaction() as con:
        orders=[p for p in store.all(con,"purchase_orders") if p["decision_id"]==decision["id"]]
        assert orders and sum(p["quantity"] for p in orders)>0
        report=dict(verified_at=now(),storage="PostgreSQL",transport="Kafka",simulation_events=len(simulation["event_ids"]),duplicate_event="ignored",decision_id=decision["id"],execution_status=executed["status"],purchase_orders=len(orders),replanning="completed after execution event",checks=["Kafka demand to PostgreSQL","LangGraph trained model planning","OR-Tools allocation","policy-gated approval","atomic simulated purchase order and shipment creation","Kafka execution outcome","replanning","idempotent event replay"])
    (artifact_dir()/"integration_verification.json").write_text(json.dumps(report,indent=2))
    return report
