# NEXUS API

The running interactive reference is http://localhost:8000/docs. OpenAPI is available at `/openapi.json`.

Create the first owner with `POST /api/v1/auth/setup` (`email`, `password`). Sign in with `POST /api/v1/auth/login`. The response sets an HttpOnly session cookie. Writes require an allowed Origin when supplied. The first owner is ADMIN. Sessions can be revoked by logout. Passwords are scrypt-hashed; there are no default credentials.

| Endpoint | Purpose |
|---|---|
| GET /health | API/storage liveness |
| GET /api/v1/snapshot | Operational dashboard and records |
| GET /api/v1/platform/status | Sources, metrics, models, execution, worker, drift, runs |
| GET /api/v1/platform/source-records/{source_id} | Namespaced source extract, limit 1–200 |
| GET /api/v1/platform/forecasts | Trained 28-day store forecasts; optional store_id |
| POST /api/v1/platform/simulate | Queue future scenario events: ticks, seed |
| POST /api/v1/platform/plan | Plan replenishment: warehouse_id, severity |
| POST /api/v1/agents/decision/{id}/approve | Review: approved boolean, reason |
| POST /api/v1/platform/execute/{id} | Idempotent execution of approved simulation actions |
| POST /api/v1/platform/reroute-plan | Propose shipment_id, warehouse_id, route, eta, reason |
| GET /api/v1/platform/rag?q=... | Grounded policy/supplier passages with citations |
| POST /api/v1/platform/documents | Add plain-text retrieval document: name, text |
| GET /api/v1/platform/dead-letters | Failed events preserved for investigation |
| POST /api/v1/platform/dead-letters/{id}/retry | Explicitly queue a replay after fixing its cause |
| GET /metrics | Prometheus counters and queue gauges |

All platform endpoints except liveness and metrics require a session. Mutations require ADMIN, MANAGER or EXECUTIVE; executive-value plans require ADMIN/EXECUTIVE approval. Structured execution policy is `policies/approval.json`. Retrieved documents cannot grant permissions.

Kafka envelope: `event_id`, `schema_version: 1`, `created_at`, `source: simulation`, `type`, plus typed payload. Topics: `nexus.simulation`, `nexus.execution`, `nexus.state`, `nexus.dead-letter`. Outbox publication is at least once, consumer effects are idempotent by event ID. Database changes and resulting outbox entries commit atomically. Offset commit occurs after persistence. The local single-partition configuration preserves simulation tick order.

Operational sample records retain their own manual bookkeeping workflows. Simulation reroutes must use approval plans. Purchase orders and carrier changes are applied to the simulated ERP only; no real vendor/transport API is configured.
