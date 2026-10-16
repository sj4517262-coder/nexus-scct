"""Leakage-controlled forecasting and delay-risk training with MLflow lineage."""
import json
import math
import os
from datetime import timedelta
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS","4")
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, roc_auc_score, brier_score_loss, accuracy_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sqlalchemy import select

from nexus.platform.config import engine, artifact_dir, RUNTIME
from nexus.platform import schema

FEATURES=["store_code","lag_1","lag_7","lag_14","lag_28","mean_7","mean_28","std_7","dow","month","day"]


def regression_metrics(actual,predicted):
    actual=np.asarray(actual,dtype=float)
    predicted=np.asarray(predicted,dtype=float)
    denominator=np.abs(actual).sum()
    return {"mae":float(mean_absolute_error(actual,predicted)),"rmse":float(mean_squared_error(actual,predicted)**.5),"wape":float(np.abs(actual-predicted).sum()/denominator*100) if denominator else None}


def features(history,codes):
    frame=history.sort_values(["store_id","date"]).copy()
    frame["date"]=pd.to_datetime(frame.date)
    frame["store_code"]=frame.store_id.map(codes)
    grouped=frame.groupby("store_id")["units"]
    for lag in (1,7,14,28):
        frame[f"lag_{lag}"]=grouped.shift(lag)
    for width in (7,28):
        frame[f"mean_{width}"]=grouped.transform(lambda s:s.shift(1).rolling(width).mean())
    frame["std_7"]=grouped.transform(lambda s:s.shift(1).rolling(7).std())
    frame["dow"]=frame.date.dt.dayofweek
    frame["month"]=frame.date.dt.month
    frame["day"]=frame.date.dt.day
    return frame.dropna(subset=FEATURES)


def recursive_forecast(history,codes,model=None,horizon=28):
    output=[]
    for store_id,group in history.sort_values("date").groupby("store_id"):
        values=list(group.units.astype(float))
        last=pd.Timestamp(group.date.max())
        for step in range(1,horizon+1):
            day=last+timedelta(days=step)
            row=dict(store_code=codes[store_id],lag_1=values[-1],lag_7=values[-7],lag_14=values[-14],lag_28=values[-28],mean_7=np.mean(values[-7:]),mean_28=np.mean(values[-28:]),std_7=np.std(values[-7:],ddof=1),dow=day.dayofweek,month=day.month,day=day.day)
            value=float(model.predict(pd.DataFrame([row],columns=FEATURES))[0]) if model is not None else values[-7]
            value=max(0,value)
            values.append(value)
            output.append(dict(store_id=store_id,date=day,forecast=value))
    return pd.DataFrame(output)


def score_predictions(actual,predictions):
    joined=actual.merge(predictions,on=["store_id","date"],validate="one_to_one")
    if len(joined)!=len(actual):
        raise ValueError("Forecast evaluation missing observations")
    return regression_metrics(joined.units,joined.forecast),joined


def mlflow_setup():
    import mlflow
    RUNTIME.mkdir(exist_ok=True,parents=True)
    tracking_uri=os.getenv("NEXUS_MLFLOW_URI","sqlite:///"+(RUNTIME/"mlflow.db").as_posix())
    mlflow.set_tracking_uri(tracking_uri)
    experiment=mlflow.get_experiment_by_name("NEXUS verified models")
    if experiment is None:
        mlflow.create_experiment("NEXUS verified models",**({} if tracking_uri.startswith("http") else {"artifact_location":(RUNTIME/"mlflow-artifacts").as_uri()}))
    mlflow.set_experiment("NEXUS verified models")
    return mlflow


def train_demand(db_engine=None):
    with (db_engine or engine()).connect() as con:
        history=pd.read_sql(select(schema.store_daily),con)
    history["date"]=pd.to_datetime(history.date)
    dates=sorted(history.date.unique())
    if len(dates)<140:
        raise ValueError("At least 140 days of M5 store history are required")
    codes={s:i for i,s in enumerate(sorted(history.store_id.unique()))}
    train=history[history.date<dates[-56]].copy()
    validation=history[(history.date>=dates[-56])&(history.date<dates[-28])].copy()
    test=history[history.date>=dates[-28]].copy()
    params=dict(max_iter=160,max_leaf_nodes=15,learning_rate=.06,l2_regularization=2,random_state=42,early_stopping=False)
    model=HistGradientBoostingRegressor(**params)
    prepared=features(train,codes)
    model.fit(prepared[FEATURES],prepared.units)
    candidate_val,_=score_predictions(validation,recursive_forecast(train,codes,model))
    baseline_val,_=score_predictions(validation,recursive_forecast(train,codes))
    selected="gradient_boosting" if candidate_val["wape"]<baseline_val["wape"] else "seasonal_naive"
    # Refit on train+validation, then evaluate the untouched final 28 days once.
    pretest=history[history.date<dates[-28]]
    prepared=features(pretest,codes)
    model.fit(prepared[FEATURES],prepared.units)
    candidate_test,candidate_join=score_predictions(test,recursive_forecast(pretest,codes,model))
    baseline_test,baseline_join=score_predictions(test,recursive_forecast(pretest,codes))
    selected_join=candidate_join if selected=="gradient_boosting" else baseline_join
    errors=np.abs(selected_join.units-selected_join.forecast)
    interval=float(np.quantile(errors,.9))
    # A future model trained on all available data; test metrics stay separate.
    prepared=features(history,codes)
    model.fit(prepared[FEATURES],prepared.units)
    future=recursive_forecast(history,codes,model if selected=="gradient_boosting" else None)
    summary=dict(kind="demand",source_id="m5",grain="store/day",selected_model=selected,features=FEATURES,train_start=str(train.date.min().date()),train_end=str(train.date.max().date()),validation_start=str(validation.date.min().date()),validation_end=str(validation.date.max().date()),test_start=str(test.date.min().date()),test_end=str(test.date.max().date()),validation={"candidate":candidate_val,"baseline":baseline_val},test={"candidate":candidate_test,"baseline":baseline_test},selection_rule="lowest validation WAPE; final test never used for selection",evaluation="recursive 28-day multi-step forecast, lag features use only available history or prior predictions",train_rows=len(train),test_rows=len(test),store_count=len(codes),interval_method="90th percentile absolute holdout error; empirical, not a coverage guarantee",interval_width=interval,as_of=str(history.date.max().date()))
    mlflow=mlflow_setup()
    with mlflow.start_run(run_name="m5-store-demand") as run:
        summary["run_id"]=run.info.run_id
        mlflow.log_params({**params,"source":"m5","selected":selected,"horizon":28,"grain":"store/day","train_end":summary["train_end"]})
        for split in ("validation","test"):
            for variant,measurements in summary[split].items():
                mlflow.log_metrics({f"{split}_{variant}_{key}":value for key,value in measurements.items() if value is not None})
        mlflow.log_dict(summary,"evaluation.json")
        bundle=dict(model=model,codes=codes,history=history,summary=summary)
        joblib.dump(bundle,artifact_dir()/"demand.joblib")
        mlflow.log_artifact(str(artifact_dir()/"demand.joblib"))
    future["date"]=future.date.dt.strftime("%Y-%m-%d")
    future["lower"]=np.maximum(0,future.forecast-interval)
    future["upper"]=future.forecast+interval
    (artifact_dir()/"demand_forecasts.json").write_text(future.to_json(orient="records"))
    (artifact_dir()/"demand_model.json").write_text(json.dumps(summary,indent=2))
    return summary


def order_level_logistics(db_engine=None):
    with (db_engine or engine()).connect() as con:
        raw=pd.read_sql(select(schema.logistics),con)
    raw["order_date"]=pd.to_datetime(raw.order_date)
    # DataCo rows are order lines. Keep entire orders in one time partition.
    return raw.groupby("order_id",as_index=False).agg(order_date=("order_date","min"),shipping_mode=("shipping_mode","first"),market=("market","first"),region=("region","first"),scheduled_days=("scheduled_days","first"),quantity=("quantity","sum"),sales=("sales","sum"),actual_days=("actual_days","max"),late=("late","max"))


RISK_COLUMNS=["shipping_mode","market","region","scheduled_days","quantity","sales"]


def train_risk(db_engine=None):
    frame=order_level_logistics(db_engine).sort_values("order_date")
    dates=sorted(frame.order_date.unique())
    if len(dates)<30:
        raise ValueError("At least 30 days of logistics history required")
    cut=dates[int(len(dates)*.8)]
    train=frame[frame.order_date<cut]
    test=frame[frame.order_date>=cut]
    if train.late.nunique()<2 or test.late.nunique()<2:
        raise ValueError("Risk train/test splits need both outcome classes")
    preprocessing=ColumnTransformer([("categories",OneHotEncoder(handle_unknown="ignore"),RISK_COLUMNS[:3]),("numbers",StandardScaler(),RISK_COLUMNS[3:])])
    model=Pipeline([("features",preprocessing),("classifier",LogisticRegression(max_iter=500,random_state=42))])
    model.fit(train[RISK_COLUMNS],train.late)
    probability=model.predict_proba(test[RISK_COLUMNS])[:,1]
    base=float(train.late.mean())
    measurements=dict(roc_auc=float(roc_auc_score(test.late,probability)),brier=float(brier_score_loss(test.late,probability)),accuracy=float(accuracy_score(test.late,probability>=.5)),baseline_brier=float(brier_score_loss(test.late,np.full(len(test),base))),baseline_accuracy=float(accuracy_score(test.late,np.full(len(test),int(base>=.5)))))
    summary=dict(kind="delay_risk",source_id="dataco",grain="order",model="logistic_regression",features=RISK_COLUMNS,excluded_features=["actual_days","late","delivery_status","shipping_date"],train_start=str(train.order_date.min().date()),train_end=str(train.order_date.max().date()),test_start=str(test.order_date.min().date()),test_end=str(test.order_date.max().date()),train_rows=len(train),test_rows=len(test),metrics=measurements,training_late_rate=base,semantics="Delivery delay probability; not supplier financial failure probability",reference={"scheduled_days_mean":float(train.scheduled_days.mean()),"quantity_mean":float(train.quantity.mean()),"sales_mean":float(train.sales.mean()),"shipping_modes":sorted(train.shipping_mode.unique())})
    mlflow=mlflow_setup()
    with mlflow.start_run(run_name="dataco-delay-risk") as run:
        summary["run_id"]=run.info.run_id
        mlflow.log_params({"source":"dataco","model":"logistic_regression","split":"chronological 80/20 by unique date","grain":"order"})
        mlflow.log_metrics(measurements)
        mlflow.log_dict(summary,"evaluation.json")
        joblib.dump(dict(model=model,summary=summary),artifact_dir()/"risk.joblib")
        mlflow.log_artifact(str(artifact_dir()/"risk.joblib"))
    (artifact_dir()/"risk_model.json").write_text(json.dumps(summary,indent=2))
    # Empirical patterns are simulation inputs, never cross-source entity links.
    patterns=dict(source_id="dataco",historical_orders=len(frame),late_rate=float(frame.late.mean()),lead_time_days=[int(v) for v in frame.actual_days.sample(min(1000,len(frame)),random_state=42)],shipping_modes=frame.shipping_mode.value_counts(normalize=True).to_dict(),quantity_quantiles={str(q):float(frame.quantity.quantile(q)) for q in (.25,.5,.75,.95)})
    (artifact_dir()/"logistics_patterns.json").write_text(json.dumps(patterns,indent=2))
    return summary


def train_all():
    return {"demand":train_demand(),"risk":train_risk()}


def summaries():
    result={}
    for name in ("demand","risk"):
        path=artifact_dir()/f"{name}_model.json"
        result[name]=json.loads(path.read_text()) if path.exists() else None
    return result


def demand_forecast(store_id=None):
    path=artifact_dir()/"demand_forecasts.json"
    if not path.exists():
        raise ValueError("Train the demand model first")
    rows=json.loads(path.read_text())
    return [row for row in rows if store_id is None or row["store_id"]==store_id]


def delay_probability(features):
    path=artifact_dir()/"risk.joblib"
    if not path.exists():
        raise ValueError("Train the delay-risk model first")
    bundle=joblib.load(path)
    probability=float(bundle["model"].predict_proba(pd.DataFrame([features],columns=RISK_COLUMNS))[0,1])
    return {"probability":probability,"model_run_id":bundle["summary"]["run_id"],"source_id":"dataco","application":"simulation scenario; not a real cross-company prediction"}
