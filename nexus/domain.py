"""Transparent operational calculations and deterministic planning."""
import math
import statistics
from datetime import date, timedelta
from nexus.store import now, uid

AGENTS = [
    ("Planner", "Synthesizes disruption response plans"),
    ("Inventory", "Checks warehouse capacity and stock balance"),
    ("Logistics", "Identifies shipment exposure"),
    ("Supplier Risk", "Evaluates supplier concentration and risk"),
    ("Demand Forecasting", "Computes a weekly seasonal baseline"),
    ("Escalation", "Routes all material plans to human review"),
    ("KPI Monitor", "Computes metrics from recorded operations"),
    ("Executive Summary", "Summarizes operational exceptions"),
]


def risk_level(score):
    return "CRITICAL" if score >= 75 else "HIGH" if score >= 50 else "MEDIUM" if score >= 25 else "LOW"


def warehouse_view(w):
    utilization = round(100*w["stock"]/w["capacity"], 1)
    return {**w, "utilization": utilization, "status": "CRITICAL" if utilization >= 90 or utilization < 15 else "WARNING" if utilization >= 80 or utilization < 30 else "OPTIMAL"}


def metrics(data):
    shipments, warehouses, suppliers = [data[k] for k in ("shipments", "warehouses", "suppliers")]
    delivered = [s for s in shipments if s["status"] == "DELIVERED"]
    on_time = [s for s in delivered if s["delivered_at"][:10] <= s["eta"]]
    active = [s for s in shipments if s["status"] != "DELIVERED"]
    late = [s for s in active if s["status"] == "DELAYED" or s["eta"] < str(date.today())]
    capacity = sum(w["capacity"] for w in warehouses)
    units = sum(s["quantity"] for s in shipments)
    return dict(
        on_time_delivery=round(100*len(on_time)/len(delivered), 1) if delivered else None,
        warehouse_utilization=round(100*sum(w["stock"] for w in warehouses)/capacity, 1) if capacity else 0,
        transport_cost_per_unit=round(sum(s["cost_usd"] for s in shipments)/units, 2) if units else 0,
        delayed_shipments=len(late), active_shipments=len(active), delivered_shipments=len(delivered),
        high_risk_suppliers=sum(s["risk_score"] >= 50 for s in suppliers),
        active_disruptions=sum(d["status"] == "ACTIVE" for d in data["disruptions"]),
        pending_decisions=sum(d["status"] == "PENDING" for d in data["decisions"]),
        total_stock=sum(w["stock"] for w in warehouses),
    )


def forecast(history, horizon=28):
    history = sorted(history, key=lambda r: r["date"])[-90:]
    if len(history) < 14:
        return {"model": "Weekly seasonal baseline", "history": history, "points": [], "warning": "At least 14 daily observations are required."}
    values = [r["quantity"] for r in history]
    weekdays = {i: [] for i in range(7)}
    for row in history[-28:]:
        weekdays[date.fromisoformat(row["date"]).weekday()].append(row["quantity"])
    means = {k: statistics.mean(v) if v else statistics.mean(values[-7:]) for k, v in weekdays.items()}
    residuals = [r["quantity"]-means[date.fromisoformat(r["date"]).weekday()] for r in history[-28:]]
    sigma = max(1, statistics.pstdev(residuals))
    # Backtest last seven observations using only earlier observations.
    training = history[:-7]
    errors = []
    for r in history[-7:]:
        same_day = [x["quantity"] for x in training[-28:] if date.fromisoformat(x["date"]).weekday() == date.fromisoformat(r["date"]).weekday()]
        if same_day and r["quantity"] > 0:
            errors.append(abs(statistics.mean(same_day)-r["quantity"])/r["quantity"]*100)
    last_day = date.fromisoformat(history[-1]["date"])
    points = []
    for i in range(1, horizon+1):
        day = last_day+timedelta(days=i)
        mean = means[day.weekday()]
        width = 1.645*sigma*math.sqrt(1+i/7)
        points.append(dict(date=str(day), forecast=round(mean), lower=max(0, round(mean-width)), upper=round(mean+width)))
    return dict(model="Weekly seasonal baseline", interval="Approximate 90% prediction range", history=history[-28:], points=points, backtest_mape=round(statistics.mean(errors), 2) if errors else None, data_source="sample" if all(r["source"] == "sample" for r in history) else "imported / mixed", as_of=history[-1]["date"])


def recommendations(warehouses):
    # Sequentially reserve projected stock so all suggested transfers can coexist.
    projected = {w["id"]: w["stock"] for w in warehouses}
    plans = []
    for source in sorted(warehouses, key=lambda w: w["stock"]/w["capacity"], reverse=True):
        excess = projected[source["id"]]-int(source["capacity"]*.8)
        if excess <= 0:
            continue
        for dest in sorted(warehouses, key=lambda w: projected[w["id"]]/w["capacity"]):
            if dest["id"] == source["id"]:
                continue
            room = int(dest["capacity"]*.75)-projected[dest["id"]]
            quantity = min(excess, max(0, room))
            if quantity:
                plans.append(dict(from_warehouse=source["id"], to_warehouse=dest["id"], quantity=quantity, reason="Reduce source occupancy to 80% while keeping destination at or below 75%."))
                projected[source["id"]] -= quantity
                projected[dest["id"]] += quantity
                excess -= quantity
            if excess <= 0:
                break
    return plans


def orchestrate(store, con, disruption, actor):
    affected = set(disruption["affected_entities"])
    warehouses = store.all(con, "warehouses")
    exposed = [s for s in store.all(con, "shipments") if s["supplier_id"] in affected and s["status"] != "DELIVERED"]
    risky = [s for s in store.all(con, "suppliers") if s["id"] in affected]
    fc = forecast(store.all(con, "demand"), 7)
    reports = {
        "Inventory": f"{sum(warehouse_view(w)['status'] != 'OPTIMAL' for w in warehouses)} warehouses require attention.",
        "Logistics": f"{len(exposed)} active shipments directly exposed.",
        "Supplier Risk": f"{len(risky)} suppliers affected; {sum(s['risk_score'] >= 50 for s in risky)} high risk.",
        "Demand Forecasting": f"Next 7 days baseline: {sum(p['forecast'] for p in fc['points']):,} units.",
        "Escalation": "Human review required before plan acceptance. External execution is not connected.",
        "KPI Monitor": "Operational metrics recalculated from persisted records.",
    }
    action = f"Review {len(exposed)} exposed shipments and contingency supply for {disruption['title']}"
    reports["Planner"] = action
    reports["Executive Summary"] = " ".join(reports[k] for k in ("Logistics", "Supplier Risk", "Inventory"))
    decision = dict(id=uid("DEC"), disruption_id=disruption["id"], agent="Planner", action=action, reasoning=reports["Executive Summary"]+" "+reports["Escalation"], confidence=0.8, value_usd=disruption["estimated_impact_usd"], status="PENDING", created_at=now(), reviewed_by=None)
    store.put(con, "decisions", decision)
    for name, _ in AGENTS:
        store.put(con, "agent_runs", dict(id=name, result=reports[name], last_run=now(), disruption_id=disruption["id"]))
    store.event(con, "DECISION", action, actor, decision["id"], disruption["severity"], {"reports": reports})
    return decision
