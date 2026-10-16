"""Reproducible ingestion. Native IDs always retain their source namespace."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sqlalchemy import select, func

from nexus.platform import schema
from nexus.platform.config import ROOT, engine, artifact_dir

DATACO_URL = "https://raw.githubusercontent.com/ashishpatel26/DataCo-SMART-SUPPLY-CHAIN-FOR-BIG-DATA-ANALYSIS/main/DataCoSupplyChainDataset.csv"
SF_URL = "https://data.sf.gov/resource/p5r5-fd7g.json"


def digest(path):
    result = hashlib.sha256()
    with open(path,"rb") as file:
        for block in iter(lambda:file.read(1024*1024),b""):
            result.update(block)
    return result.hexdigest()


def download(url,path,params=None):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+".part")
    with requests.get(url,params=params,timeout=(20,120),stream=True) as response:
        response.raise_for_status()
        with temporary.open("wb") as file:
            for block in response.iter_content(1024*1024):
                file.write(block)
    temporary.replace(path)
    return path


def record_source(connection,source_id,name,url,license,manifest):
    manifest={**manifest,"retrieved_at":datetime.now(timezone.utc).isoformat(),"namespace":source_id,"cross_source_entity_join":False}
    schema.upsert_frame(connection,schema.sources,pd.DataFrame([dict(source_id=source_id,name=name,url=url,license=license,manifest=json.dumps(manifest))]))
    return manifest


def ingest_m5(raw_dir=None,days=365,db_engine=None):
    db_engine=db_engine or engine()
    schema.initialize(db_engine)
    raw_dir=Path(raw_dir or ROOT/"data/raw/m5")
    sales_path=raw_dir/"sales_train_validation.csv"
    calendar_path=raw_dir/"calendar.csv"
    price_path=raw_dir/"sell_prices.csv"
    cal=pd.read_csv(calendar_path)
    sales=pd.read_csv(sales_path)
    price=pd.read_csv(price_path)
    day_columns=sorted([c for c in sales if c.startswith("d_")],key=lambda c:int(c[2:]))
    if not day_columns:
        raise ValueError("No M5 daily demand columns")
    checks={
        "unique_item_store": not sales.duplicated(["item_id","store_id"]).any(),
        "consistent_product_metadata": sales.groupby("item_id")[["dept_id","cat_id"]].nunique().max().max()==1,
        "consistent_store_metadata": sales.groupby("store_id")["state_id"].nunique().max()==1,
        "calendar_unique": not cal.duplicated("d").any() and not cal.duplicated("date").any(),
        "calendar_complete":set(day_columns).issubset(set(cal.d)),
        "nonnegative_integer_demand": bool((sales[day_columns].to_numpy()>=0).all() and all(pd.api.types.is_integer_dtype(sales[c]) for c in day_columns)),
        "price_keys_unique":not price.duplicated(["item_id","store_id","wm_yr_wk"]).any(),
        "prices_positive":bool((price.sell_price>0).all()),
        "price_weeks_known":set(price.wm_yr_wk).issubset(set(cal.wm_yr_wk)),
    }
    known=set(zip(sales.item_id,sales.store_id))
    checks["price_series_known"]=set(zip(price.item_id,price.store_id)).issubset(known)
    checks={key:bool(value) for key,value in checks.items()}
    if not all(checks.values()):
        raise ValueError(f"M5 validation failed: {checks}")
    products=sales[["item_id","dept_id","cat_id"]].drop_duplicates().rename(columns={"item_id":"native_id","dept_id":"department","cat_id":"category"})
    products["product_id"]="m5:product:"+products.native_id
    products["source_id"]="m5"
    stores=sales[["store_id","state_id"]].drop_duplicates().rename(columns={"store_id":"native_id","state_id":"state"})
    stores["store_id"]="m5:store:"+stores.native_id
    stores["source_id"]="m5"
    pairs=pd.DataFrame({"series_id":"m5:series:"+sales.item_id+":"+sales.store_id,"product_id":"m5:product:"+sales.item_id,"store_id":"m5:store:"+sales.store_id})
    calendar=cal[["d","date","wm_yr_wk"]].rename(columns={"d":"day","wm_yr_wk":"week"})
    calendar["date"]=pd.to_datetime(calendar.date).dt.date
    chosen=day_columns[-days:] if days else day_columns
    selected_weeks=set(cal.loc[cal.d.isin(chosen),"wm_yr_wk"])
    selected_prices=price[price.wm_yr_wk.isin(selected_weeks)].copy()
    price_frame=pd.DataFrame({"series_id":"m5:series:"+selected_prices.item_id+":"+selected_prices.store_id,"week":selected_prices.wm_yr_wk,"price":selected_prices.sell_price})
    grouped=sales.groupby("store_id")[day_columns].sum().reset_index().melt(id_vars="store_id",var_name="day",value_name="units")
    grouped["date"]=grouped.day.map(dict(zip(cal.d,pd.to_datetime(cal.date).dt.date)))
    grouped["store_id"]="m5:store:"+grouped.store_id
    manifest=dict(files={p.name:digest(p) for p in (sales_path,calendar_path,price_path)},checks=checks,products=len(products),stores=len(stores),series=len(pairs),raw_days=len(day_columns),imported_product_days=len(chosen),expected_demand_rows=len(pairs)*len(chosen),forecast_grain="store/day",mapping="m5 item/store IDs are namespaced; stores are not silently relabelled as demo warehouses")
    with db_engine.begin() as con:
        previous=con.execute(select(schema.sources.c.manifest).where(schema.sources.c.source_id=="m5")).scalar_one_or_none()
        previous=json.loads(previous) if previous else {}
        if previous.get("files")==manifest["files"] and previous.get("imported_product_days")==len(chosen):
            count=int(con.execute(select(func.count()).select_from(schema.demand)).scalar_one())
            if count==manifest["expected_demand_rows"]:
                manifest["persisted_demand_rows"]=count
                (artifact_dir()/"m5_validation.json").write_text(json.dumps(manifest,indent=2))
                return manifest
        record_source(con,"m5","M5 retail demand","https://www.kaggle.com/competitions/m5-forecasting-accuracy/data","M5 competition terms; user-supplied files",manifest)
        for table,frame in [(schema.products,products),(schema.stores,stores),(schema.series,pairs),(schema.calendar,calendar),(schema.store_daily,grouped[["store_id","date","units"]]),(schema.prices,price_frame)]:
            schema.upsert_frame(con,table,frame)
        # Bounded-memory conversion; each chunk has unique series/day keys.
        for start in range(0,len(sales),1500):
            chunk=sales.iloc[start:start+1500]
            frame=chunk[["item_id","store_id",*chosen]].melt(id_vars=["item_id","store_id"],var_name="day",value_name="units")
            frame["series_id"]="m5:series:"+frame.item_id+":"+frame.store_id
            schema.upsert_frame(con,schema.demand,frame[["series_id","day","units"]])
        manifest["persisted_demand_rows"]=int(con.execute(select(func.count()).select_from(schema.demand)).scalar_one())
    (artifact_dir()/"m5_validation.json").write_text(json.dumps(manifest,indent=2))
    return manifest


def ingest_public(refresh=False,po_limit=20000,db_engine=None):
    db_engine=db_engine or engine()
    schema.initialize(db_engine)
    path=ROOT/"data/raw/dataco/DataCoSupplyChainDataset.csv"
    if refresh or not path.exists():
        download(DATACO_URL,path)
    columns=["Order Item Id","Order Id","order date (DateOrders)","Shipping Mode","Market","Order Region","Category Name","Days for shipment (scheduled)","Days for shipping (real)","Order Item Quantity","Sales","Late_delivery_risk"]
    raw=pd.read_csv(path,encoding="latin1",usecols=columns)
    dates=pd.to_datetime(raw["order date (DateOrders)"],errors="coerce")
    if dates.isna().any() or raw["Order Item Id"].duplicated().any():
        raise ValueError("Invalid DataCo dates or duplicate order-line keys")
    frame=pd.DataFrame(dict(id="dataco:line:"+raw["Order Item Id"].astype(str),source_id="dataco",order_id="dataco:order:"+raw["Order Id"].astype(str),order_date=dates.dt.date,shipping_mode=raw["Shipping Mode"],market=raw["Market"],region=raw["Order Region"],category=raw["Category Name"],scheduled_days=raw["Days for shipment (scheduled)"],actual_days=raw["Days for shipping (real)"],quantity=raw["Order Item Quantity"],sales=raw["Sales"],late=raw["Late_delivery_risk"]))
    if (frame[["scheduled_days","actual_days","quantity"]]<0).any().any() or not set(frame.late).issubset({0,1}):
        raise ValueError("DataCo measurements outside valid range")
    po_path=ROOT/"data/raw/sf/procurement.json"
    # Source row identifiers keep department/accounting splits distinct.
    params={"$select":":id,purchase_order,vendor,department,fiscal_year,vouchers_paid,vouchers_pending","$order":":id","$limit":po_limit}
    if refresh or not po_path.exists():
        download(SF_URL,po_path,params)
    po_raw=pd.read_json(po_path,dtype=False)
    po=pd.DataFrame(dict(id="sf:row:"+po_raw[":id"].astype(str),source_id="sf_procurement",native_order_id=po_raw.purchase_order.fillna("UNSPECIFIED"),vendor=po_raw.vendor.fillna("UNSPECIFIED"),department=po_raw.department.fillna("UNSPECIFIED"),fiscal_year=pd.to_numeric(po_raw.fiscal_year),paid_usd=pd.to_numeric(po_raw.vouchers_paid),pending_usd=pd.to_numeric(po_raw.vouchers_pending)))
    manifests={}
    with db_engine.begin() as con:
        manifests["dataco"]=record_source(con,"dataco","DataCo historical order lines","https://data.mendeley.com/datasets/8gx2fvg2k6/5","CC BY 4.0",dict(authors="Fabian Constante, Fernando Silva, António Pereira",download_url=DATACO_URL,mirror=True,sha256=digest(path),rows=len(frame),grain="order line",personal_columns="excluded from normalized data",start=str(frame.order_date.min()),end=str(frame.order_date.max())))
        schema.upsert_frame(con,schema.logistics,frame)
        manifests["sf_procurement"]=record_source(con,"sf_procurement","San Francisco vendor payments by purchase order","https://data.sf.gov/d/p5r5-fd7g","Open Data Commons PDDL 1.0",dict(download_url=SF_URL,query=params,sha256=digest(po_path),rows=len(po),coverage="bounded source extract",grain="purchase-order accounting row; not a line-item order or shipment",amount_semantics="actual paid/pending amounts; not invented unit prices"))
        schema.upsert_frame(con,schema.procurement,po)
    (artifact_dir()/"public_sources.json").write_text(json.dumps(manifests,indent=2))
    return manifests


def source_status(db_engine=None):
    db_engine=db_engine or engine()
    schema.initialize(db_engine)
    with db_engine.connect() as con:
        return [{**dict(row),"manifest":json.loads(row["manifest"])} for row in con.execute(select(schema.sources)).mappings()]
