"""Atomic execution in the explicit simulation ERP; no real vendor side effects."""
from datetime import date,timedelta
from nexus.store import now,uid
from nexus.platform.intelligence import policy


def execute_decision(store,con,decision_id,actor="execution-worker"):
    decision=store.get(con,"decisions",decision_id)
    if not decision:
        raise ValueError("Decision not found")
    if decision["status"]=="EXECUTED":
        return decision
    if decision["status"] not in {"APPROVED","AUTO_APPROVED"}:
        raise ValueError("Only approved decisions can execute")
    rules=policy()
    if decision.get("source")!="simulation" or rules["execution_mode"]!="SIMULATION":
        raise ValueError("Built-in execution is restricted to simulation records")
    if decision.get("action_type") not in rules["allowed_actions"] or decision["value_usd"]>rules["max_plan_value_usd"]:
        raise ValueError("Execution blocked by current policy")
    if decision.get("policy",{}).get("version")!=rules["version"]:
        raise ValueError("Policy changed; plan must be reviewed again")
    if decision["status"]=="AUTO_APPROVED" and (decision["value_usd"]>rules["auto_approve_max_usd"] or decision["confidence"]<rules["minimum_confidence"] or decision.get("severity")=="CRITICAL"):
        raise ValueError("Decision no longer meets automatic approval policy")
    payload=decision["payload"]
    action_type=decision["action_type"]
    created=[]
    if action_type=="PURCHASE_ORDER":
        warehouse=store.get(con,"warehouses",payload["warehouse_id"])
        if not warehouse or warehouse.get("source")!="simulation":
            raise ValueError("Invalid simulation destination")
        allocations=payload["allocations"]
        if not allocations or any(a["quantity"]<=0 or a["unit_cost"]<=0 for a in allocations):
            raise ValueError("Invalid procurement allocation")
        computed=sum(a["quantity"]*a["unit_cost"] for a in allocations)
        if abs(computed-decision["value_usd"])>.01:
            raise ValueError("Order value differs from the approved plan")
        incoming=sum(s["quantity"] for s in store.all(con,"shipments") if s["warehouse_id"]==warehouse["id"] and s["status"]!="DELIVERED")
        if warehouse["stock"]+incoming+sum(a["quantity"] for a in allocations)>warehouse["capacity"]:
            raise ValueError("Destination no longer has capacity including inbound commitments")
        for allocation in allocations:
            supplier=store.get(con,"suppliers",allocation["supplier_id"])
            if not supplier or supplier.get("source")!="simulation" or allocation["quantity"]>supplier["order_capacity"]:
                raise ValueError("Supplier availability changed since approval")
            if decision["status"]=="AUTO_APPROVED" and allocation.get("delay_probability",1)>=rules["maximum_delay_probability"]:
                raise ValueError("Delay risk exceeds automatic approval threshold")
        for allocation in allocations:
            order=dict(id=uid("SIM-PO"),source="simulation",decision_id=decision_id,supplier_id=allocation["supplier_id"],warehouse_id=warehouse["id"],quantity=allocation["quantity"],unit_cost=allocation["unit_cost"],value_usd=allocation["quantity"]*allocation["unit_cost"],status="ISSUED",created_at=now(),executed_by=actor)
            store.put(con,"purchase_orders",order)
            shipment=dict(id=uid("SIM-SHP"),source="simulation",purchase_order_id=order["id"],tracking_number=order["id"],supplier_id=order["supplier_id"],warehouse_id=warehouse["id"],carrier="Simulation logistics",quantity=order["quantity"],cost_usd=round(order["quantity"]*.1,2),status="IN_TRANSIT",eta=str(date.today()+timedelta(days=allocation["lead_days"])),delivered_at=None,route="Optimized simulation sourcing",updated_at=now(),simulation_lead_days=allocation["lead_days"])
            shipment["created_tick"]=warehouse.get("last_simulation_tick",0)
            scenario=store.get(con,"meta","simulation")
            if scenario:
                shipment["eta"]=str(date.fromisoformat(scenario["created_at"][:10])+timedelta(days=shipment["created_tick"]+allocation["lead_days"]))
            store.put(con,"shipments",shipment)
            created.append(order["id"])
    elif action_type=="REROUTE":
        shipment=store.get(con,"shipments",payload["shipment_id"])
        destination=store.get(con,"warehouses",payload["warehouse_id"])
        if not shipment or shipment.get("source")!="simulation" or shipment["status"]=="DELIVERED":
            raise ValueError("Shipment is unavailable for simulated rerouting")
        if not destination or destination.get("source")!="simulation":
            raise ValueError("Invalid simulation destination")
        incoming=sum(s["quantity"] for s in store.all(con,"shipments") if s["warehouse_id"]==destination["id"] and s["status"]!="DELIVERED" and s["id"]!=shipment["id"])
        if destination["stock"]+incoming+shipment["quantity"]>destination["capacity"]:
            raise ValueError("Destination capacity unavailable")
        original_destination=shipment["warehouse_id"]
        shipment.update(warehouse_id=destination["id"],route=payload["route"],eta=payload["eta"],status="REROUTED",updated_at=now())
        store.put(con,"shipments",shipment)
        if original_destination!=destination["id"]:
            store.enqueue(con,"nexus.state",dict(type="execution.completed",source="simulation",decision_id=decision_id,warehouse_id=original_destination),identifier=f"executed:{decision_id}:origin")
        created.append(shipment["id"])
    elif action_type=="INVENTORY_TRANSFER":
        source=store.get(con,"warehouses",payload["from_warehouse"])
        dest=store.get(con,"warehouses",payload["to_warehouse"])
        qty=payload["quantity"]
        if not source or not dest or source.get("source")!="simulation" or dest.get("source")!="simulation" or source["id"]==dest["id"] or qty<=0 or source["stock"]<qty or dest["stock"]+qty>dest["capacity"]:
            raise ValueError("Transfer is no longer feasible")
        source["stock"]-=qty
        dest["stock"]+=qty
        for warehouse in (source,dest):
            warehouse["updated_at"]=now()
            store.put(con,"warehouses",warehouse)
    decision.update(status="EXECUTED",executed_at=now(),executed_by=actor,execution_entities=created)
    store.put(con,"decisions",decision)
    store.event(con,"EXECUTION",f"Executed simulated {action_type}: {decision['action']}",actor,decision_id,details={"created":created,"mode":"SIMULATION"})
    store.enqueue(con,"nexus.state",dict(type="execution.completed",source="simulation",decision_id=decision_id,warehouse_id=decision.get("warehouse_id") or payload.get("warehouse_id") or payload.get("to_warehouse"),entities=created),identifier=f"executed:{decision_id}")
    return decision
