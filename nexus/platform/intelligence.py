"""LangGraph model/tool orchestration with policy-grounded retrieval and OR-Tools."""
import hashlib
import json
import time
from pathlib import Path
from typing import TypedDict

import numpy as np
from langgraph.graph import StateGraph, END
from ortools.linear_solver import pywraplp
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from nexus.store import now, uid
from nexus.platform.config import ROOT
from nexus.platform.models import demand_forecast, delay_probability, summaries


def policy():
    return json.loads((ROOT/"policies/approval.json").read_text())


def retrieve(question, extra_documents=(), limit=4):
    chunks=[]
    for path in sorted((ROOT/"policies").glob("*.md")):
        for index,part in enumerate(path.read_text(encoding="utf-8").split("\n\n")):
            if len(part.strip())>40:
                chunks.append(dict(source=path.name,chunk=index,text=part.strip(),sha256=hashlib.sha256(part.encode()).hexdigest()))
    for doc in extra_documents:
        for index,part in enumerate(doc["text"].split("\n\n")):
            if len(part.strip())>20:
                chunks.append(dict(source=doc["name"],chunk=index,text=part.strip(),sha256=hashlib.sha256(part.encode()).hexdigest()))
    if not chunks:
        return []
    matrix=TfidfVectorizer(stop_words="english",ngram_range=(1,2)).fit_transform([c["text"] for c in chunks]+[question])
    scores=cosine_similarity(matrix[-1],matrix[:-1])[0]
    indices=np.argsort(scores)[::-1][:limit]
    return [{**chunks[i],"score":round(float(scores[i]),4)} for i in indices if scores[i]>0]


def optimize_procurement(quantity,suppliers,budget):
    solver=pywraplp.Solver.CreateSolver("SCIP")
    if solver is None:
        raise RuntimeError("OR-Tools SCIP solver is unavailable")
    solver.SetTimeLimit(5000)
    allocations=[solver.IntVar(0,int(s["order_capacity"]),s["id"]) for s in suppliers]
    solver.Add(sum(allocations)>=quantity)
    solver.Add(sum(x*s["unit_cost"] for x,s in zip(allocations,suppliers))<=budget)
    solver.Minimize(sum(x*s["unit_cost"]*(1+s["delay_probability"]) for x,s in zip(allocations,suppliers)))
    status=solver.Solve()
    if status not in (pywraplp.Solver.OPTIMAL,pywraplp.Solver.FEASIBLE):
        return {"feasible":False,"reason":"Available supplier capacity or policy budget cannot cover the shortfall","allocations":[]}
    result=[dict(supplier_id=s["id"],quantity=round(x.solution_value()),unit_cost=s["unit_cost"],lead_days=s["lead_days"],delay_probability=s["delay_probability"]) for x,s in zip(allocations,suppliers) if x.solution_value()>.5]
    return dict(feasible=True,solver="OR-Tools SCIP",optimal=status==pywraplp.Solver.OPTIMAL,allocations=result,total_cost=sum(a["quantity"]*a["unit_cost"] for a in result),objective=solver.Objective().Value())


def evaluate_policy(value,confidence,risk,severity,action_type):
    rules=policy()
    if action_type not in rules["allowed_actions"] or value>rules["max_plan_value_usd"]:
        return dict(status="BLOCKED",required_role="ADMIN",reason="Action type or amount exceeds execution policy",version=rules["version"])
    automatic=value<=rules["auto_approve_max_usd"] and confidence>=rules["minimum_confidence"] and risk<rules["maximum_delay_probability"] and severity!="CRITICAL"
    return dict(status="AUTO_APPROVED" if automatic else "PENDING",required_role="EXECUTIVE" if value>=rules["executive_review_min_usd"] else "MANAGER",reason="Within bounded automatic policy" if automatic else "Human review required by value, uncertainty, risk, or severity",version=rules["version"])


class PlanningState(TypedDict,total=False):
    warehouse:dict
    suppliers:list
    inbound:int
    severity:str
    documents:list
    forecast:dict
    risk:list
    citations:list
    optimization:dict
    plan:dict
    policy:dict
    reports:dict


def build_graph():
    def forecast_node(state):
        rows=demand_forecast(state["warehouse"]["m5_store_id"])
        if not rows:
            raise ValueError("No trained forecast for scenario M5 store")
        daily=sum(r["forecast"] for r in rows)/len(rows)
        return {"forecast":{"daily_units":daily,"source":"m5","model_run_id":summaries()["demand"]["run_id"],"history_as_of":summaries()["demand"]["as_of"]},"reports":{"Demand Forecasting":f"Historical M5 store baseline {daily:,.0f} units/day applied to this simulated scenario."}}
    def risk_node(state):
        results=[]
        for supplier in state["suppliers"]:
            scored=delay_probability(supplier["scenario_features"])
            results.append({**supplier,"delay_probability":scored["probability"],"risk_run_id":scored["model_run_id"]})
        return {"risk":results,"reports":{**state["reports"],"Supplier Risk":f"Scored {len(results)} simulation suppliers using the trained delay model."}}
    def retrieval_node(state):
        citations=retrieve("inventory replenishment supplier capacity approval critical shipment execution",state.get("documents",[]))
        return {"citations":citations,"reports":{**state["reports"],"Policy Retrieval":f"Retrieved {len(citations)} policy/supplier passages. Structured policy remains authoritative."}}
    def inventory_node(state):
        available=state["warehouse"]["stock"]+state["inbound"]
        target=min(state["warehouse"]["capacity"],round(state["forecast"]["daily_units"]*7))
        needed=max(0,target-available)
        return {"plan":{"quantity":needed,"target":target,"available":available},"reports":{**state["reports"],"Inventory":f"Target {target:,}; stock plus inbound {available:,}; shortfall {needed:,}."}}
    def optimization_node(state):
        result=optimize_procurement(state["plan"]["quantity"],state["risk"],policy()["max_plan_value_usd"]) if state["plan"]["quantity"] else {"feasible":True,"allocations":[],"total_cost":0,"solver":"OR-Tools SCIP"}
        return {"optimization":result,"reports":{**state["reports"],"Logistics":f"OR-Tools sourcing {'feasible' if result['feasible'] else 'infeasible'}; {len(result['allocations'])} allocations."}}
    def planner_node(state):
        result=state["optimization"]
        confidence=.9 if result["feasible"] else 0
        worst=max((a["delay_probability"] for a in result["allocations"]),default=0)
        decision=evaluate_policy(result.get("total_cost",0),confidence,worst,state["severity"],"PURCHASE_ORDER")
        if not result["feasible"]:
            decision.update(status="BLOCKED",reason=result["reason"])
        return {"policy":decision,"reports":{**state["reports"],"Planner":"Sourcing plan constructed with recorded model provenance.","Escalation":decision["reason"]}}
    def summary_node(state):
        return {"reports":{**state["reports"],"Executive Summary":f"Replenish {state['plan']['quantity']:,} units; estimated cost ${state['optimization'].get('total_cost',0):,.2f}; {state['policy']['status']}."}}
    graph=StateGraph(PlanningState)
    nodes=[("forecast_agent",forecast_node),("risk_agent",risk_node),("retrieval_agent",retrieval_node),("inventory_agent",inventory_node),("optimization_agent",optimization_node),("planner_agent",planner_node),("summary_agent",summary_node)]
    for name,node in nodes:
        graph.add_node(name,node)
    graph.set_entry_point(nodes[0][0])
    for (name,_),(next_name,_) in zip(nodes,nodes[1:]):
        graph.add_edge(name,next_name)
    graph.add_edge(nodes[-1][0],END)
    return graph.compile()


def plan_replenishment(store,con,warehouse_id,trigger="operator",severity="MEDIUM"):
    warehouse=store.get(con,"warehouses",warehouse_id)
    if not warehouse or warehouse.get("source")!="simulation":
        raise ValueError("Planning requires a simulation warehouse with an explicit M5 mapping")
    existing=[d for d in store.all(con,"decisions") if d.get("warehouse_id")==warehouse_id and d["status"] in {"PENDING","APPROVED","AUTO_APPROVED"} and d.get("action_type")=="PURCHASE_ORDER"]
    if existing:
        return existing[0]
    suppliers=[s for s in store.all(con,"suppliers") if s.get("source")=="simulation"]
    inbound=sum(s["quantity"] for s in store.all(con,"shipments") if s["warehouse_id"]==warehouse_id and s["status"]!="DELIVERED")
    start=time.perf_counter()
    result=build_graph().invoke(dict(warehouse=warehouse,suppliers=suppliers,inbound=inbound,severity=severity,documents=store.all(con,"documents")),config={"recursion_limit":20})
    run_id=uid("RUN")
    run=dict(id=run_id,warehouse_id=warehouse_id,trigger=trigger,created_at=now(),duration_ms=round((time.perf_counter()-start)*1000),status="COMPLETED",engine="LangGraph",reports=result["reports"],model_provenance=result["forecast"],citations=result["citations"])
    store.put(con,"planning_runs",run)
    for name,report in result["reports"].items():
        store.put(con,"agent_runs",dict(id=name,result=report,last_run=now(),run_id=run_id,engine="LangGraph"))
    if not result["plan"]["quantity"]:
        store.event(con,"REPLAN","Replanning complete: existing stock and inbound commitments meet target",entity_id=warehouse_id,details={"run_id":run_id})
        return {"status":"NO_ACTION","run_id":run_id}
    decision=dict(id=uid("DEC"),disruption_id=None,agent="LangGraph Planner",action_type="PURCHASE_ORDER",warehouse_id=warehouse_id,action=f"Replenish {warehouse['name']} with {result['plan']['quantity']:,} units",reasoning=result["reports"]["Executive Summary"],confidence=.9 if result["optimization"]["feasible"] else 0,value_usd=result["optimization"].get("total_cost",0),status=result["policy"]["status"],created_at=now(),reviewed_by=None,severity=severity,payload={"allocations":result["optimization"]["allocations"],"warehouse_id":warehouse_id},policy=result["policy"],run_id=run_id,citations=result["citations"],source="simulation")
    store.put(con,"decisions",decision)
    store.event(con,"DECISION",decision["action"],entity_id=decision["id"],severity=severity,details={"policy":decision["policy"],"run_id":run_id})
    if decision["status"]=="AUTO_APPROVED":
        store.enqueue(con,"nexus.execution",{"type":"decision.approved","decision_id":decision["id"],"source":"simulation"})
    return decision
