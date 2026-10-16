"""Transactional outbox + idempotent consumer, bounded retries and dead letters."""
import json
import logging
import os
import time
from datetime import date,timedelta

from confluent_kafka import Producer,Consumer,KafkaException
from confluent_kafka.admin import AdminClient,NewTopic

from nexus.store import Store,now
from nexus.platform.config import database_url,load_local_env
from nexus.platform.intelligence import plan_replenishment
from nexus.platform.execution import execute_decision

log=logging.getLogger("nexus.streaming")
TOPICS=["nexus.simulation","nexus.execution","nexus.state","nexus.dead-letter"]


def bootstrap():
    load_local_env()
    return os.getenv("NEXUS_KAFKA_BOOTSTRAP","localhost:19092")


def ensure_topics():
    admin=AdminClient({"bootstrap.servers":bootstrap()})
    current=admin.list_topics(timeout=15).topics
    missing=[NewTopic(t,num_partitions=1,replication_factor=1) for t in TOPICS if t not in current]
    if not missing:
        return
    pending=admin.create_topics(missing)
    for result in pending.values():
        result.result(timeout=15)


def publish_pending(store,producer,limit=50):
    count=0
    with store.transaction() as con:
        rows=con.execute("SELECT * FROM outbox WHERE status='PENDING' ORDER BY created_at,id LIMIT ?",(limit,)).fetchall()
        for row in rows:
            delivered=[]
            errors=[]
            try:
                def callback(error,message):
                    errors.append(str(error)) if error else delivered.append(True)
                producer.produce(row["topic"],key=row["id"],value=row["payload"],on_delivery=callback)
                producer.flush(5)
                if not delivered:
                    raise RuntimeError("; ".join(errors) or "Kafka delivery not acknowledged")
                con.execute("UPDATE outbox SET status='PUBLISHED',attempts=attempts+1,last_error=NULL WHERE id=?",(row["id"],))
                count+=1
            except Exception as exc:
                con.execute("UPDATE outbox SET attempts=attempts+1,last_error=? WHERE id=?",(str(exc)[:500],row["id"]))
                break
    return count


def process_event(store,payload):
    identifier=payload.get("event_id")
    if not isinstance(identifier,str) or not identifier or payload.get("schema_version")!=1 or payload.get("source")!="simulation":
        raise ValueError("Invalid event envelope or source")
    with store.transaction() as con:
        if con.execute("SELECT id FROM inbox WHERE id=?",(identifier,)).fetchone():
            return {"status":"DUPLICATE"}
        kind=payload.get("type")
        if kind=="simulation.tick":
            warehouse=store.get(con,"warehouses",payload.get("warehouse_id"))
            units=payload.get("demand_units")
            if not warehouse or warehouse.get("source")!="simulation" or not isinstance(units,int) or units<0:
                raise ValueError("Invalid simulation warehouse or demand")
            # Kafka preserves ordering per partition. Inbox protects replay; sequence protects late events.
            tick=int(payload["tick"])
            if tick<=warehouse.get("last_simulation_tick",0):
                raise ValueError("Out-of-order simulation tick")
            before=warehouse["stock"]
            fulfilled=min(before,units)
            warehouse["stock"]-=fulfilled
            warehouse.update(last_simulation_tick=tick,updated_at=now())
            monitor=store.get(con,"monitoring","demand_drift") or {"id":"demand_drift","window":[]}
            baseline=float(payload.get("baseline_units",units))
            monitor["window"]=(monitor["window"]+[{"actual":units,"predicted":baseline}])[-100:]
            total=sum(x["actual"] for x in monitor["window"])
            monitor["wape"]=100*sum(abs(x["actual"]-x["predicted"]) for x in monitor["window"])/total if total else None
            monitor["status"]="ALERT" if monitor["wape"] is not None and monitor["wape"]>35 else "NORMAL"
            monitor["updated_at"]=now()
            store.put(con,"monitoring",monitor)
            store.put(con,"warehouses",warehouse)
            store.event(con,"DEMAND",f"Simulation demand {units:,}; fulfilled {fulfilled:,}; shortage {units-fulfilled:,}",entity_id=warehouse["id"],severity="HIGH" if units>fulfilled else "LOW",details={"source":"simulation","tick":tick,"event_id":identifier,"provenance":payload["provenance"]})
            for shipment in store.all(con,"shipments"):
                if shipment.get("source")!="simulation" or shipment["warehouse_id"]!=warehouse["id"] or shipment["status"]=="DELIVERED":
                    continue
                shipment.setdefault("created_tick",tick)
                elapsed=tick-shipment["created_tick"]
                delay=payload["delay_draw"]<payload["historical_delay_rate"]
                # Fix an arrival lead time once per shipment using source observations.
                shipment.setdefault("actual_simulation_lead_days",max(1,round((shipment.get("simulation_lead_days",4)+payload.get("sampled_lead_days",4))/2))+(2 if delay else 0))
                if elapsed>=shipment["actual_simulation_lead_days"]:
                    if warehouse["stock"]+shipment["quantity"]<=warehouse["capacity"]:
                        warehouse["stock"]+=shipment["quantity"]
                        shipment.update(status="DELIVERED",delivered_at=payload["provenance"]["future_date"],updated_at=now())
                        po=store.get(con,"purchase_orders",shipment.get("purchase_order_id"))
                        if po:
                            po.update(status="RECEIVED",received_at=now())
                            store.put(con,"purchase_orders",po)
                        store.event(con,"SHIPMENT",f"Simulation received {shipment['quantity']:,} units",entity_id=shipment["id"])
                elif delay:
                    shipment.update(status="DELAYED",updated_at=now())
                store.put(con,"shipments",shipment)
            store.put(con,"warehouses",warehouse)
            plan_replenishment(store,con,warehouse["id"],trigger=identifier,severity="CRITICAL" if units>fulfilled else "MEDIUM")
        elif kind=="decision.approved":
            execute_decision(store,con,payload["decision_id"])
        elif kind=="execution.completed":
            if payload.get("warehouse_id"):
                plan_replenishment(store,con,payload["warehouse_id"],trigger=identifier)
        elif kind=="dead_letter":
            pass
        else:
            raise ValueError("Unsupported event type")
        con.execute("INSERT INTO inbox VALUES(?,?)",(identifier,now()))
        store.put(con,"monitoring",dict(id="consumer",last_success=now(),last_event=identifier,status="HEALTHY"))
    return {"status":"PROCESSED"}


def dead_letter(store,payload,error):
    import hashlib
    serialized=json.dumps(payload,sort_keys=True)
    identifier=payload.get("event_id") or hashlib.sha256(serialized.encode()).hexdigest()
    with store.transaction() as con:
        con.execute("INSERT INTO dead_letters VALUES(?,?,?,?) ON CONFLICT(id) DO NOTHING",(identifier,serialized,str(error)[:2000],now()))
        store.enqueue(con,"nexus.dead-letter",dict(type="dead_letter",source="simulation",original_event_id=identifier,error=str(error)[:500]),identifier="dlq:"+identifier)
        store.event(con,"FAILURE","Event moved to dead-letter queue",entity_id=identifier,severity="HIGH",details={"error":str(error)[:500]})
        store.put(con,"planning_runs",dict(id="FAILED:"+identifier,warehouse_id=payload.get("warehouse_id"),trigger=identifier,created_at=now(),status="FAILED",engine="event worker",duration_ms=0,reports={"Failure":str(error)[:500]}))


def worker():
    logging.basicConfig(level=logging.INFO)
    store=Store(database_url())
    store.initialize()
    ensure_topics()
    producer=Producer({"bootstrap.servers":bootstrap(),"enable.idempotence":True,"delivery.timeout.ms":10000})
    consumer=Consumer({"bootstrap.servers":bootstrap(),"group.id":"nexus-state-v1","auto.offset.reset":"earliest","enable.auto.commit":False,"max.poll.interval.ms":900000})
    consumer.subscribe(TOPICS[:3])
    log.info("NEXUS event worker ready")
    try:
        while True:
            with store.transaction() as con:
                store.put(con,"monitoring",dict(id="worker",heartbeat=now(),status="RUNNING"))
            publish_pending(store,producer)
            message=consumer.poll(.5)
            if message is None:
                with store.transaction() as con:
                    store.put(con,"monitoring",dict(id="worker",heartbeat=now(),status="RUNNING"))
                continue
            if message.error():
                log.error("Kafka: %s",message.error())
                continue
            payload={}
            for attempt in range(3):
                try:
                    payload=json.loads(message.value())
                    if not isinstance(payload,dict):
                        raise ValueError("Event must be an object")
                    process_event(store,payload)
                    consumer.commit(message=message,asynchronous=False)
                    break
                except (ValueError,KeyError,TypeError) as exc:
                    dead_letter(store,payload if isinstance(payload,dict) else {"raw":str(payload)},exc)
                    consumer.commit(message=message,asynchronous=False)
                    break
                except Exception as exc:
                    log.exception("Event failed on attempt %s",attempt+1)
                    if attempt==2:
                        # If persistence is unavailable this raises and leaves the offset uncommitted.
                        dead_letter(store,payload,exc)
                        consumer.commit(message=message,asynchronous=False)
                    else:
                        time.sleep(attempt+1)
    except KeyboardInterrupt:
        pass
    finally:
        producer.flush(5)
        consumer.close()
