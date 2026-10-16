# NEXUS Supply Chain Control Tower — 4.0

A working supply-chain simulation platform with a Next.js dashboard, FastAPI, PostgreSQL, Kafka, MLflow, LangGraph, grounded document retrieval and OR-Tools. The seven-phase implementation connects historical datasets to trained forecasts, scenario events, reviewed plans, simulated execution and replanning.

## Start the completed project

Docker Desktop must be running. From this folder:

```powershell
python scripts/deploy.py up
```

Open http://localhost:3000 and create your owner account. There are no default credentials. On a fresh clone, follow the bootstrap instructions below to prepare data and models. MLflow is at http://localhost:5001; API documentation is at http://localhost:8000/docs.

For a fresh installation, put `sales_train_validation.csv`, `calendar.csv`, and `sell_prices.csv` from the [M5 competition](https://www.kaggle.com/competitions/m5-forecasting-accuracy/data) in `data/raw/m5`, then run:

```powershell
python scripts/deploy.py bootstrap
```

This builds containers, validates/imports M5, downloads public logistics/procurement extracts, trains models, logs experiments and starts the application. The default product history is 365 days (11.1 million rows); all 1,913 days are retained at store/day forecasting grain. A full product-history import is available with `scripts/manage.py m5 --days 0`. Allow significant time and disk space for ingestion. Repeated identical imports are checked and reused.

## Project interview handbook

Read the [clickable PDF handbook](output/pdf/NEXUS_Interview_Handbook.pdf), [Markdown edition](docs/NEXUS_Interview_Handbook.md), or download the [offline HTML edition](docs/NEXUS_Interview_Handbook.html). These cover the implementation, design decisions, limitations, 60 interview questions and practical exercises.

Local credentials, raw datasets, trained binary models, database backups and generated runtime files are excluded from Git. Bootstrap regenerates the runtime artifacts. Saved validation results describe the original local verification; they are not a claim that every fresh installation has already passed those checks.

## Seven phases delivered

| Phase | Implementation |
|---|---|
| 1. Data foundation | 3,049 M5 products, 10 stores, 30,490 product/store series; foreign-key relationships, source namespaces, file hashes and validation reports; 11,128,850 product/day observations imported |
| 2. Forecasting | Lag/rolling/calendar features, chronological train/validation/test, recursive 28-day evaluation, seasonal baseline, WAPE/MAE/RMSE, trained artifacts and MLflow experiments |
| 3. Logistics/procurement | 180,519 DataCo shipment/order lines and 20,000 San Francisco purchase-order accounting rows; separate source IDs, attribution, source browser and explicit grain |
| 4. Live simulator | Seeded future demand and delay scenarios, Kafka event publication, PostgreSQL operational updates, deliveries and inventory changes |
| 5. Intelligence | LangGraph forecast/risk/retrieval/inventory/optimization/planning/summary steps; trained delay-risk model; cited policy/supplier passages; OR-Tools integer sourcing optimization |
| 6. Execution loop | Structured approval limits, executive review thresholds, idempotent simulated purchase orders and shipment reroutes, transaction checks, execution events and replanning |
| 7. Delivery | Backend and browser tests, full-stack verification, monitoring, retries/dead letters, CI, container deployment, backup launcher and operating documentation |

## Measured model results

The selected store-level gradient-boosting model achieved **5.92% test WAPE**, **250.30 MAE** and **349.81 RMSE** on March 28–April 24, 2016. The weekly seasonal baseline achieved 10.75% WAPE, 454.22 MAE and 643.28 RMSE. Selection used the preceding validation period, not the final test. Future forecasts start after the historical source cutoff of April 24, 2016; simulation projects those patterns into a labelled future scenario.

DataCo delay-risk logistic regression achieved **0.733 ROC-AUC**, **0.196 Brier score** and **69.27% accuracy** on a chronological order-level holdout, versus 55.05% baseline accuracy. It predicts delivery delay, not supplier financial failure. Full metrics, feature definitions, dates and MLflow run IDs are in `runtime/artifacts/*_model.json` and the Forecasting screen.

## Use the application

1. Open **Platform lab → Data foundation** to inspect checks and source provenance.
2. Open **Demand forecasting** to inspect the trained model, holdout comparisons and forecasts.
3. In **Platform lab → Simulation**, advance one day or seven days. Kafka processes the events and agents create sourcing plans.
4. Open **Decision center**, review a simulation plan and approve/reject with a reason. Approved plans execute through the worker.
5. Inspect **Purchase orders**, **Shipments**, **Agent runs**, and **Event stream** for execution and replanning evidence.
6. Use **Knowledge & policies** to retrieve cited passages or add supplier/policy text. Structured policy remains authoritative.
7. Use **Monitoring** for worker health, backlog, failures, drift and retry controls.

The operational dashboard also includes sample suppliers, warehouse transfers, disruption reports, manual tracking records, a network view, CSV export, account sessions and a grounded operational copilot. Sample narrative disruption plans are labelled bookkeeping workflows; simulation plans have executable typed payloads. Simulation nodes are clearly named `Simulation · ...` and mapped to M5 stores as scenario projections.

## Data provenance and boundaries

[M5](https://www.kaggle.com/competitions/m5-forecasting-accuracy/data) inputs were already supplied in this workspace and remain subject to competition terms. [DataCo](https://data.mendeley.com/datasets/8gx2fvg2k6/5), by Fabian Constante, Fernando Silva and António Pereira, is CC BY 4.0; the manifest records the public download mirror and file hash. Normalized data excludes personal columns. [San Francisco vendor payments by purchase order](https://data.sf.gov/d/p5r5-fd7g) is a bounded public accounting extract, not item-level purchase orders or shipment records. Its source manifest records the query, hash and PDDL attribution.

These datasets are independent. No unrelated companies, vendors, products or purchase orders are falsely joined. Synthetic supplier costs/capacities are documented assumptions. Forecasting and inventory planning operate at store/aggregate-unit grain; SKU-level history is retained for analysis. Retrieval uses TF-IDF with extractive cited answers and needs no paid LLM key. Policy instructions in documents cannot change execution permissions.

The built-in ERP and carrier execution are **simulation**. Orders, shipment changes and inventory updates persist and emit real Kafka events, but they do not spend money or contact real suppliers. Connecting an actual company's ERP/carrier is a separate integration requiring that company's credentials and contracts.

## Development and verification

Use Python 3.11 and Node.js 20 or newer:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-platform.txt
npm ci
.venv\Scripts\python.exe -m pytest -q
npm run lint
npm run build
npx playwright install chromium
npm run test:e2e
python scripts/deploy.py verify
```

See [API documentation](docs/API.md), [operations and recovery](docs/OPERATIONS.md), and the generated integration report under `runtime/artifacts`. The archived prototype vision and experimental modules are retained separately (`README.prototype.md`, `main_research.py`, `requirements-research.txt`, `docker-compose.research.yml`) and are not required by the completed application.
