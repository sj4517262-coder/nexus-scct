"""Seeded scenario events informed by M5 demand and DataCo delay distributions."""
import json
import random
from datetime import date,timedelta

from nexus.store import Store,now,uid
from nexus.platform.config import database_url,artifact_dir
from nexus.platform.models import demand_forecast,summaries


def initialize_scenario(store,con):
    existing=store.get(con,"meta","simulation")
    if existing:
        return existing
    forecasts=demand_forecast()
    store_ids=sorted({r["store_id"] for r in forecasts})
    for index,store_id in enumerate(store_ids):
        daily=sum(r["forecast"] for r in forecasts if r["store_id"]==store_id)/28
        warehouse=dict(id=f"SIM-WH-{index+1:02}",name=f"Simulation · {store_id.split(':')[-1]}",source="simulation",m5_store_id=store_id,capacity=round(daily*30),stock=round(daily*3),lat=34+index*.8,lng=-120+index*2,updated_at=now(),provenance={"demand_source":"m5","mapping_type":"synthetic scenario projection; not a real M5 warehouse"})
        store.put(con,"warehouses",warehouse)
    for index,(cost,lead,capacity,mode) in enumerate([(4.2,4,500000,"Standard Class"),(5.1,2,300000,"First Class"),(3.8,6,800000,"Second Class")],1):
        supplier=dict(id=f"SIM-SUP-{index:02}",source="simulation",name=f"Simulation supplier {index}",country="Synthetic",category="Simulation replenishment",risk_score=25,monthly_volume=capacity,lat=30+index,lng=-100-index,unit_cost=cost,lead_days=lead,order_capacity=capacity,updated_at=now(),scenario_features=dict(shipping_mode=mode,market="USCA",region="West of USA",scheduled_days=lead,quantity=10,sales=200))
        store.put(con,"suppliers",supplier)
    meta=dict(id="simulation",created_at=now(),tick=0,source_ids=["m5","dataco","sf_procurement"],forecast_as_of=summaries()["demand"]["as_of"],mode="Historical patterns projected into an explicitly synthetic future scenario")
    store.put(con,"meta",meta)
    store.event(con,"SIMULATION","Initialized synthetic nodes with explicit historical-source mappings")
    return meta


def simulate(ticks=10,seed=42,store=None):
    if not 1<=ticks<=1000:
        raise ValueError("Ticks must be between 1 and 1,000")
    store=store or Store(database_url())
    store.initialize()
    pattern=json.loads((artifact_dir()/"logistics_patterns.json").read_text())
    forecasts=demand_forecast()
    with store.transaction() as con:
        meta=initialize_scenario(store,con)
        warehouses=[w for w in store.all(con,"warehouses") if w.get("source")=="simulation"]
        identifiers=[]
        for _ in range(ticks):
            meta["tick"]+=1
            tick=meta["tick"]
            rng=random.Random(seed+tick)
            for warehouse in warehouses:
                rows=[r for r in forecasts if r["store_id"]==warehouse["m5_store_id"]]
                predicted=rows[(tick-1)%len(rows)]["forecast"]
                units=max(0,round(predicted*rng.uniform(.8,1.2)))
                identifier=f"simulation:{meta['created_at']}:{tick}:{warehouse['id']}"
                store.enqueue(con,"nexus.simulation",dict(type="simulation.tick",source="simulation",tick=tick,warehouse_id=warehouse["id"],demand_units=units,baseline_units=predicted,delay_draw=rng.random(),historical_delay_rate=pattern["late_rate"],sampled_lead_days=rng.choice(pattern["lead_time_days"]),seed=seed,provenance={"demand":"m5","logistics":"dataco","future_date":str(date.fromisoformat(meta["created_at"][:10])+timedelta(days=tick)),"historical_forecast_as_of":meta["forecast_as_of"]}),identifier)
                identifiers.append(identifier)
        store.put(con,"meta",meta)
    return dict(ticks=ticks,events=len(identifiers),last_tick=meta["tick"],status="QUEUED",mode="SIMULATION",event_ids=identifiers)
