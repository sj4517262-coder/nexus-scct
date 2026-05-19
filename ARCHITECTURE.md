# NEXUS Supply Chain Control Tower — Architecture Diagrams

## System Architecture

```mermaid
graph TB
    subgraph CLIENT["🖥️ Client Layer"]
        FE["Next.js 14 Frontend<br/>TypeScript · Tailwind · ShadCN"]
        MOBILE["Mobile App<br/>React Native (Roadmap)"]
    end

    subgraph GATEWAY["🔀 API Gateway / Reverse Proxy"]
        NGINX["NGINX<br/>SSL · Rate Limiting · Load Balancing"]
    end

    subgraph API["⚡ Application Layer"]
        FASTAPI["FastAPI Backend<br/>REST + WebSocket · JWT Auth · RBAC"]
        CELERY["Celery Workers<br/>Async Task Processing"]
        BEAT["Celery Beat<br/>Scheduled Jobs"]
    end

    subgraph AGENTS["🤖 Multi-Agent AI Layer"]
        ORCH["LangGraph Orchestrator<br/>Master Workflow Engine"]
        PLAN["Planner Agent<br/>Strategy Synthesis"]
        INV["Inventory Agent<br/>Stock Optimization"]
        LOG["Logistics Agent<br/>Route Planning"]
        RISK["Supplier Risk Agent<br/>XGBoost Scoring"]
        DEMAND["Demand Forecast Agent<br/>TFT Model Inference"]
        ESC["Escalation Agent<br/>Human-in-the-Loop"]
        KPI["KPI Monitor Agent<br/>Threshold Alerting"]
        EXEC["Executive Summary Agent<br/>C-Suite Reporting"]
    end

    subgraph STREAMING["📡 Event Streaming"]
        KAFKA["Apache Kafka<br/>Event Bus · 6 Topics"]
        ZK["Zookeeper<br/>Cluster Coordination"]
        REDIS["Redis<br/>Cache · Pub/Sub · Sessions"]
    end

    subgraph ML["🧠 ML Engine Layer"]
        TFT["TFT Demand Forecasting<br/>PyTorch · 28-Day Horizon"]
        RL["RL Inventory Optimizer<br/>PPO · Stable-Baselines3"]
        VRP["Route Optimizer<br/>OR-Tools VRP Solver"]
        XGBOOST["Supplier Risk Model<br/>XGBoost + Graph Analytics"]
        GRAPH["Network Graph<br/>NetworkX · Cascade Simulation"]
    end

    subgraph DATA["💾 Data Layer"]
        PG["PostgreSQL 16<br/>Primary Database"]
        MLFLOW["MLflow<br/>Model Registry · Experiment Tracking"]
        DVC["DVC<br/>Data Version Control"]
    end

    subgraph OBS["📊 Observability"]
        PROM["Prometheus<br/>Metrics Collection"]
        GRAFANA["Grafana<br/>Dashboards · Alerting"]
        ELK["ELK Stack<br/>Centralized Logging"]
    end

    subgraph INFRA["☸️ Infrastructure"]
        K8S["Kubernetes 1.28<br/>Container Orchestration"]
        HPA["HPA<br/>Auto-scaling 3→20 pods"]
        GHACTIONS["GitHub Actions<br/>CI/CD Pipeline"]
    end

    FE -->|HTTPS/WSS| NGINX
    MOBILE -->|HTTPS| NGINX
    NGINX -->|HTTP| FASTAPI
    FASTAPI -->|Async tasks| CELERY
    BEAT -->|Schedules| CELERY
    FASTAPI -->|Orchestrate| ORCH
    ORCH --> PLAN
    ORCH --> INV
    ORCH --> LOG
    ORCH --> RISK
    ORCH --> DEMAND
    ORCH --> ESC
    ORCH --> KPI
    ORCH --> EXEC
    FASTAPI -->|Publish| KAFKA
    KAFKA -->|Subscribe| CELERY
    KAFKA --- ZK
    FASTAPI -->|Cache/PubSub| REDIS
    INV -->|Inference| RL
    LOG -->|Optimize| VRP
    RISK -->|Score| XGBOOST
    RISK -->|Graph| GRAPH
    DEMAND -->|Forecast| TFT
    FASTAPI -->|Read/Write| PG
    CELERY -->|Read/Write| PG
    TFT -->|Track| MLFLOW
    RL -->|Track| MLFLOW
    XGBOOST -->|Track| MLFLOW
    FASTAPI -->|Metrics| PROM
    PROM -->|Visualize| GRAFANA
    FASTAPI -->|Logs| ELK
    K8S -->|Runs| FASTAPI
    K8S -->|Runs| CELERY
    HPA -->|Scales| K8S
    GHACTIONS -->|Deploy| K8S
```

---

## Agent Orchestration Flow

```mermaid
sequenceDiagram
    participant EXT as External Event
    participant KAFKA as Kafka Topic
    participant ORCH as Orchestrator
    participant SRISK as Supplier Risk Agent
    participant DFORECAST as Demand Forecast Agent
    participant INV as Inventory Agent
    participant LOG as Logistics Agent
    participant KPI as KPI Monitor Agent
    participant PLAN as Planner Agent
    participant ESC as Escalation Agent
    participant EXEC as Executive Summary Agent
    participant HUMAN as Human Operator
    participant DB as PostgreSQL

    EXT->>KAFKA: Publish disruption event
    KAFKA->>ORCH: Consume DISRUPTION_DETECTED

    Note over ORCH: Start orchestration pipeline

    ORCH->>SRISK: Analyze supplier exposure
    SRISK-->>ORCH: {risk_score, affected_suppliers, alternatives}

    ORCH->>DFORECAST: Update demand forecast
    DFORECAST-->>ORCH: {revised_forecast, confidence_intervals, drift_detected}

    par Parallel Analysis
        ORCH->>INV: Recommend inventory adjustments
        INV-->>ORCH: {reorder_qty, safety_stock_delta, rebalance_plan}
    and
        ORCH->>LOG: Optimize routing
        LOG-->>ORCH: {alt_routes, cost_delta, eta_impact}
    end

    ORCH->>KPI: Assess KPI impact
    KPI-->>ORCH: {otif_delta, fill_rate_risk, threshold_breaches}

    ORCH->>PLAN: Synthesize response strategy
    PLAN-->>ORCH: {master_plan, decisions[], total_value_at_stake}

    ORCH->>ESC: Evaluate escalation requirements
    alt Value > $5M or CRITICAL severity
        ESC-->>ORCH: {escalation_required: true, approver_level: EXECUTIVE}
        ORCH->>HUMAN: Send approval request with context
        HUMAN-->>ORCH: approve/reject with reason
    else Value < $1M and confidence > 85%
        ESC-->>ORCH: {escalation_required: false, auto_approved: true}
    end

    ORCH->>EXEC: Generate executive briefing
    EXEC-->>ORCH: {summary, kpi_impacts, actions_taken}

    ORCH->>DB: Persist all decisions + audit trail
    ORCH->>KAFKA: Publish ORCHESTRATION_COMPLETE event

    Note over ORCH: Pipeline complete in < 3 minutes
```

---

## Event Streaming Architecture

```mermaid
graph LR
    subgraph PRODUCERS["Event Producers"]
        API["FastAPI API"]
        WORKERS["Celery Workers"]
        ML["ML Engines"]
        EXT["External APIs<br/>Weather · Port · News"]
    end

    subgraph KAFKA_CLUSTER["Apache Kafka Cluster"]
        T1["supply-chain.disruptions<br/>6 partitions"]
        T2["supply-chain.inventory<br/>6 partitions"]
        T3["supply-chain.shipments<br/>6 partitions"]
        T4["supply-chain.decisions<br/>3 partitions"]
        T5["supply-chain.kpis<br/>3 partitions"]
        T6["supply-chain.alerts<br/>3 partitions"]
    end

    subgraph CONSUMERS["Consumer Groups"]
        CG1["nexus-event-processors<br/>Disruption Handler"]
        CG2["nexus-inventory-consumers<br/>Inventory Handler"]
        CG3["nexus-decision-processors<br/>Decision Handler"]
        CG4["nexus-kpi-consumers<br/>KPI Handler"]
    end

    subgraph DOWNSTREAM["Downstream Systems"]
        REDIS_PS["Redis Pub/Sub<br/>WebSocket relay"]
        AGENTS["AI Agent<br/>Orchestration"]
        NOTIFY["Notification Service<br/>Slack · Email · PagerDuty"]
        DB_WRITE["DB Writer<br/>PostgreSQL"]
    end

    subgraph WEBSOCKET["WebSocket Clients"]
        DASH["Command Center Dashboard"]
        MOBILE_WS["Mobile App"]
    end

    API --> T1
    API --> T3
    API --> T4
    WORKERS --> T2
    WORKERS --> T5
    ML --> T4
    EXT --> T1
    EXT --> T6

    T1 --> CG1
    T2 --> CG2
    T4 --> CG3
    T5 --> CG4

    CG1 --> AGENTS
    CG1 --> REDIS_PS
    CG2 --> DB_WRITE
    CG3 --> NOTIFY
    CG3 --> DB_WRITE
    CG4 --> REDIS_PS

    REDIS_PS --> DASH
    REDIS_PS --> MOBILE_WS
    AGENTS --> T4
    NOTIFY --> T6
```

---

## ML Model Lifecycle

```mermaid
graph TD
    subgraph DATA_PREP["Data Preparation"]
        RAW["Raw Supply Chain Data<br/>Transactions · Events · Logs"]
        DVC_STORE["DVC Data Store<br/>S3 / GCS"]
        VALIDATE["Data Validation<br/>Great Expectations"]
        FEATURE["Feature Engineering<br/>Time Features · Lag Features"]
    end

    subgraph TRAINING["Model Training"]
        TFT_TRAIN["TFT Training<br/>PyTorch Lightning"]
        XGB_TRAIN["XGBoost Training<br/>Supplier Risk Model"]
        RL_TRAIN["PPO Training<br/>Inventory RL Agent"]
        VRP_BUILD["OR-Tools Config<br/>Route Optimization"]
    end

    subgraph MLFLOW_REG["MLflow Registry"]
        STAGING["Staging Models<br/>Validation pending"]
        PROD_MODELS["Production Models<br/>Serving live traffic"]
        ARCHIVE["Archived Models<br/>Historical versions"]
    end

    subgraph EVAL["Model Evaluation"]
        METRICS["Performance Metrics<br/>MAPE · AUC · Reward"]
        SHADOW["Shadow Mode Testing<br/>A/B evaluation"]
        DRIFT_DET["Drift Detection<br/>Statistical tests"]
        THRESHOLDS["Quality Gates<br/>TFT MAPE < 8%<br/>XGB AUC > 88%"]
    end

    subgraph SERVING["Model Serving"]
        INFERENCE["Inference API<br/>FastAPI endpoints"]
        CACHE["Model Cache<br/>Redis warm-up"]
        FALLBACK["Heuristic Fallback<br/>If model unavailable"]
    end

    subgraph MONITORING["Continuous Monitoring"]
        PERF_MON["Performance Monitoring<br/>Prometheus metrics"]
        DRIFT_MON["Drift Monitoring<br/>Mann-Whitney tests"]
        RETRAIN["Retraining Trigger<br/>Drift rate > 10%"]
    end

    RAW --> DVC_STORE
    DVC_STORE --> VALIDATE
    VALIDATE --> FEATURE
    FEATURE --> TFT_TRAIN
    FEATURE --> XGB_TRAIN
    FEATURE --> RL_TRAIN

    TFT_TRAIN --> STAGING
    XGB_TRAIN --> STAGING
    RL_TRAIN --> STAGING
    VRP_BUILD --> PROD_MODELS

    STAGING --> EVAL
    EVAL --> METRICS
    METRICS --> SHADOW
    SHADOW --> DRIFT_DET
    DRIFT_DET --> THRESHOLDS
    THRESHOLDS -->|Pass| PROD_MODELS
    THRESHOLDS -->|Fail| ARCHIVE

    PROD_MODELS --> INFERENCE
    INFERENCE --> CACHE
    CACHE --> FALLBACK

    INFERENCE --> PERF_MON
    PERF_MON --> DRIFT_MON
    DRIFT_MON -->|Drift detected| RETRAIN
    RETRAIN --> FEATURE
```

---

## Deployment Architecture

```mermaid
graph TB
    subgraph INTERNET["🌐 Internet"]
        USERS["End Users<br/>Browsers · Mobile"]
        CDN["CloudFront CDN<br/>Static Assets"]
    end

    subgraph EDGE["🔐 Edge / Security"]
        WAF["AWS WAF<br/>DDoS Protection"]
        ALB["Application Load Balancer<br/>SSL Termination"]
    end

    subgraph K8S_CLUSTER["☸️ Kubernetes Cluster (EKS)"]
        subgraph NAMESPACE_NEXUS["namespace: nexus"]
            subgraph FE_DEPLOY["Frontend Deployment"]
                FE1["nexus-frontend pod 1"]
                FE2["nexus-frontend pod 2"]
            end
            subgraph API_DEPLOY["API Deployment (HPA: 3→20)"]
                API1["nexus-api pod 1"]
                API2["nexus-api pod 2"]
                API3["nexus-api pod 3"]
                API_N["... up to 20 pods"]
            end
            subgraph WORKER_DEPLOY["Worker Deployment (5→15)"]
                W1["nexus-worker pod 1"]
                W2["nexus-worker pod 2"]
                W_N["... scaling pods"]
            end
        end
    end

    subgraph MANAGED["☁️ Managed Services (AWS)"]
        RDS["Amazon RDS PostgreSQL<br/>Multi-AZ · Encrypted"]
        ELASTICACHE["ElastiCache Redis<br/>Cluster Mode"]
        MSK["Amazon MSK Kafka<br/>3 brokers · Multi-AZ"]
        S3["S3<br/>ML Models · Artifacts · DVC"]
        ECR["ECR<br/>Container Registry"]
    end

    subgraph MLOPS["🧠 MLOps"]
        MLFLOW_SERVER["MLflow Tracking Server<br/>Model Registry"]
        SAGEMAKER["SageMaker (Roadmap)<br/>Managed Training"]
    end

    subgraph MONITORING["📊 Observability Stack"]
        PROMETHEUS["Prometheus"]
        GRAFANA_CLOUD["Grafana Cloud"]
        DATADOG["Datadog APM (optional)"]
        SENTRY["Sentry<br/>Error Tracking"]
        PAGERDUTY["PagerDuty<br/>On-Call Alerting"]
    end

    USERS -->|HTTPS| CDN
    USERS -->|HTTPS| WAF
    CDN --> ALB
    WAF --> ALB
    ALB -->|/| FE1
    ALB -->|/| FE2
    ALB -->|/api /ws| API1
    ALB -->|/api /ws| API2
    ALB -->|/api /ws| API3

    API1 -->|Async| W1
    API2 -->|Async| W2
    API1 & API2 & API3 --> ELASTICACHE
    API1 & API2 & API3 --> RDS
    API1 & API2 & API3 --> MSK
    W1 & W2 --> RDS
    W1 & W2 --> MSK
    W1 & W2 --> S3
    W1 & W2 --> MLFLOW_SERVER
    ECR -->|Pull images| K8S_CLUSTER
    MLFLOW_SERVER --> S3
    API1 -->|Metrics| PROMETHEUS
    PROMETHEUS --> GRAFANA_CLOUD
    API1 -->|Errors| SENTRY
    GRAFANA_CLOUD -->|Alerts| PAGERDUTY
```
