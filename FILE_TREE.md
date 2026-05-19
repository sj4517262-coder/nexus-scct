# NEXUS Supply Chain Control Tower — Complete Repository File Tree
# Generated: November 2024 | Version: 2.4.0

```
nexus-supply-chain/
│
├── 📄 README.md                          # World-class project README
├── 📄 docker-compose.yml                 # Full development/staging stack (14 services)
├── 📄 pytest.ini                         # Test configuration
├── 📄 .env.example                       # Environment variable template
├── 📄 .gitignore
├── 📄 .pre-commit-config.yaml
│
├── 🐳 docker/
│   ├── Dockerfile.api                    # FastAPI backend — multi-stage build
│   ├── Dockerfile.frontend               # Next.js frontend — multi-stage build
│   ├── Dockerfile.worker                 # Celery worker — production image
│   └── Dockerfile.ml                     # ML training container with PyTorch
│
├── ⚡ backend/
│   ├── main.py                           # FastAPI app entry point — lifespan, middleware, routes
│   ├── requirements.txt                  # 60+ production Python dependencies
│   │
│   ├── api/
│   │   ├── routes/
│   │   │   ├── all_routes.py             # Disruptions, Inventory, Suppliers, KPIs, Agents
│   │   │   ├── auth.py                   # JWT auth endpoints
│   │   │   ├── forecast.py               # Demand forecasting endpoints
│   │   │   └── shipments.py              # Shipment tracking endpoints
│   │   └── websocket.py                  # WebSocket event + KPI streaming handlers
│   │
│   ├── agents/
│   │   └── orchestrator.py               # LangGraph 8-agent orchestration engine
│   │
│   ├── streaming/
│   │   └── streaming_layer.py            # Kafka producer/consumer + Redis pub/sub
│   │
│   ├── core/
│   │   └── core_modules.py               # Config, Security (JWT/RBAC), Database ORM, Logging
│   │
│   └── workers/
│       └── celery_tasks.py               # Celery app + 12 task definitions + beat schedule
│
├── 🧠 ml/
│   ├── forecast/
│   │   └── tft_model.py                  # Temporal Fusion Transformer — training + inference + drift
│   ├── risk/
│   │   └── supplier_risk_model.py        # XGBoost risk scoring + NetworkX graph analytics
│   ├── inventory/
│   │   └── rl_optimizer.py               # PPO RL agent — custom Gym environment + training
│   └── routing/
│       └── route_optimizer.py            # OR-Tools VRP solver + multi-modal route optimization
│
├── 🖥️ frontend/
│   ├── package.json                      # 40+ production dependencies
│   ├── lib/
│   │   └── types-and-api.ts              # Full TypeScript types + React Query hooks + WebSocket hooks
│   ├── app/
│   │   ├── dashboard/page.tsx            # Command Center view
│   │   ├── agents/page.tsx               # AI Agent Orchestration
│   │   ├── inventory/page.tsx            # Inventory Intelligence
│   │   ├── suppliers/page.tsx            # Supplier Risk Matrix
│   │   ├── logistics/page.tsx            # Route Optimization
│   │   ├── events/page.tsx               # Event Stream
│   │   ├── copilot/page.tsx              # AI Executive Copilot (ARIA)
│   │   └── analytics/page.tsx            # KPI Analytics
│   └── components/
│       ├── ui/                           # ShadCN components
│       ├── charts/                       # Recharts wrappers
│       ├── maps/                         # Mapbox integration
│       └── agents/                       # Agent visualization
│
├── ☸️ k8s/
│   └── deployment.yaml                   # Full K8s manifests — Deployments, Services, HPA, PDB, Ingress, RBAC
│
├── 🔧 infra/
│   ├── nginx/
│   │   └── nginx.conf                    # Production NGINX — SSL, rate limiting, WebSocket proxy
│   └── monitoring/
│       └── prometheus.yml                # Prometheus scrape config — 7 job targets
│
├── 🤖 .github/
│   └── workflows/
│       └── ci.yml                        # Full CI/CD — lint, test, build, deploy to staging + production
│
├── 🧪 tests/
│   ├── test_suite.py                     # Unit + API + Agent orchestration tests (30+ test cases)
│   └── load/
│       └── locustfile.py                 # Enterprise load testing — 500 concurrent users, SLO validation
│
├── 📜 scripts/
│   ├── seed_data.py                      # Synthetic data generator — suppliers, warehouses, shipments, demand
│   └── deploy.sh                         # One-command deployment — local/docker/k8s/staging/production
│
├── 📊 docs/
│   ├── PRD.md                            # Product Requirements Document — personas, KPIs, ROI, governance
│   └── ARCHITECTURE.md                   # 4 Mermaid architecture diagrams — system, agents, streaming, ML, deployment
│
└── 💻 SupplyChainControlTower.jsx        # Interactive React platform artifact (8 views, AI Copilot, live simulation)
```

---

## Quick Reference — Key Files by Role

### For AI/ML Engineers
- `ml/forecast/tft_model.py` — TFT training, inference, drift detection
- `ml/risk/supplier_risk_model.py` — XGBoost + graph analytics
- `ml/inventory/rl_optimizer.py` — PPO custom Gym environment
- `ml/routing/route_optimizer.py` — OR-Tools VRP
- `backend/agents/orchestrator.py` — LangGraph multi-agent system

### For Backend Engineers
- `backend/main.py` — FastAPI entry point
- `backend/api/routes/all_routes.py` — REST endpoints
- `backend/streaming/streaming_layer.py` — Kafka + Redis + WebSocket
- `backend/core/core_modules.py` — Config, security, DB models
- `backend/workers/celery_tasks.py` — Async tasks + scheduler

### For Frontend Engineers
- `frontend/lib/types-and-api.ts` — TypeScript types + React Query hooks
- `SupplyChainControlTower.jsx` — Full platform UI (8 views)
- `frontend/package.json` — Dependencies reference

### For DevOps/Platform Engineers
- `docker-compose.yml` — 14-service full stack
- `docker/Dockerfiles` — Multi-stage production images
- `k8s/deployment.yaml` — Full K8s manifests + HPA + PDB
- `infra/nginx/nginx.conf` — Production NGINX config
- `infra/monitoring/prometheus.yml` — Observability config
- `.github/workflows/ci.yml` — GitHub Actions CI/CD
- `scripts/deploy.sh` — Deployment automation

### For Product Managers
- `docs/PRD.md` — Full PRD with personas, KPIs, ROI, governance
- `docs/ARCHITECTURE.md` — System diagrams for stakeholder presentations
- `README.md` — Executive summary, roadmap, business impact

---

## Service Ports Reference

| Service         | Port  | Purpose                    |
|-----------------|-------|----------------------------|
| nexus-api       | 8000  | FastAPI REST + WebSocket   |
| nexus-frontend  | 3000  | Next.js Platform UI        |
| postgres        | 5432  | Primary database           |
| redis           | 6379  | Cache + pub/sub            |
| kafka           | 9092  | Event streaming            |
| kafka-ui        | 8080  | Kafka management UI        |
| mlflow          | 5000  | Model registry + tracking  |
| prometheus      | 9090  | Metrics collection         |
| grafana         | 3001  | Observability dashboards   |
| nginx           | 80/443| Reverse proxy + SSL        |

---

## Environment Variables Summary

```bash
# Core
SECRET_KEY=                  # JWT signing key (32+ chars)
ENVIRONMENT=                 # development|staging|production
DATABASE_URL=                # PostgreSQL async connection string
REDIS_URL=                   # Redis connection string

# AI APIs
ANTHROPIC_API_KEY=           # Claude API for agents + ARIA copilot
OPENAI_API_KEY=              # Fallback LLM

# Kafka
KAFKA_BOOTSTRAP_SERVERS=     # Kafka broker addresses

# MLflow
MLFLOW_TRACKING_URI=         # MLflow tracking server URL

# Frontend
NEXT_PUBLIC_API_URL=         # Backend API URL
NEXT_PUBLIC_MAPBOX_TOKEN=    # Mapbox GL JS access token
```

---

## Setup Commands Reference

```bash
# 1. Clone and configure
git clone https://github.com/your-org/nexus-supply-chain.git
cd nexus-supply-chain && cp .env.example .env

# 2. Local development
./scripts/deploy.sh local

# 3. Full Docker stack
./scripts/deploy.sh docker

# 4. Kubernetes (staging)
./scripts/deploy.sh staging

# 5. Seed data
python scripts/seed_data.py --suppliers 50 --warehouses 12 --shipments 300

# 6. Train ML models
python ml/forecast/tft_model.py --epochs 50
python ml/risk/supplier_risk_model.py
python ml/inventory/rl_optimizer.py --timesteps 2000000

# 7. Run tests
pytest tests/ -v --tb=short

# 8. Load test
locust -f tests/load/locustfile.py --headless -u 500 -r 50 --run-time 5m

# 9. Health check
./scripts/deploy.sh health
```
