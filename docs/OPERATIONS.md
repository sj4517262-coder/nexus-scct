# Deployment and operations

Use `python scripts/deploy.py bootstrap` for a fresh database (Docker Desktop/Linux Docker Compose required). Place the three M5 inputs in `data/raw/m5` first. `python scripts/deploy.py up` restarts an already prepared installation. The launcher generates `.env.platform` with a random database secret if absent. Never commit this file. `down` preserves named volumes; `status` lists service health; `verify` exercises the real simulation loop.

The stack runs PostgreSQL on 5433, Kafka on 19092, API on 8000, Next.js on 3000, and MLflow on 5001. Published ports bind to loopback. Kafka's internal listener is 29092. Historical artifacts are mounted at `runtime/artifacts`; normalized data and operational state are in PostgreSQL. MLflow has its own persistent volume. Existing legacy development containers are independent of this stack.

All Python runtime requirements and frontend direct dependencies are pinned. `npm ci` uses the committed lockfile. Containers run as unprivileged users. For internet hosting, supply a hostname/TLS reverse proxy, update allowed origins, enable secure cookies, and provision production secrets and authenticated service access. The delivered deployment is the complete local simulation environment, not an unrequested public cloud service.

## Recovery

- Worker or Kafka failure: pending outbox rows remain in PostgreSQL. Docker restarts workers; publication resumes when Kafka returns. Consumer offsets are committed only after database success. Duplicate delivery is harmless.
- Bad payload or exhausted processing retries: preserve error and payload in dead letters. Inspect Monitoring; correct the cause before requesting replay. Late simulation ticks are deliberately rejected rather than rewriting newer inventory.
- Policy version changes invalidate old approvals at execution. Rejected or blocked plans cannot execute. Changed stock/capacity is rechecked atomically.
- Monitoring: worker heartbeat, queue backlog, dead letters, API errors, agent duration/failure history, model experiment metrics, and rolling simulation demand WAPE. A >35% rolling WAPE triggers the in-app drift alert. Historical model accuracy is not a guarantee for a future scenario.
- Model retraining: `docker compose --env-file .env.platform -f docker-compose.platform.yml run --rm bootstrap python scripts/manage.py train`. Keep the prior artifacts and MLflow run IDs for rollback; retrain on new representative history before applying to another business.

## Backup and restore

`python scripts/deploy.py backup` produces a consistent custom-format PostgreSQL dump under `runtime/backups`. Preserve `runtime/artifacts`, `.env.platform`, and the `platform-mlflow` named volume separately. Restore into a separate test database with `pg_restore` before replacing a running installation. Do not use `docker compose down -v` unless you intentionally want to destroy persisted data.

## Verification

`python -m pytest -q` checks backend, policies, optimization, leakage, idempotence and rollback. Install `requirements-platform.txt` first. `npm run lint` and `npm run build` verify the UI. `npx playwright install chromium` and `npm run test:e2e` run isolated browser workflows on ports 3100/8100. Set `NEXUS_TEST_BROWSER=chrome` to use installed Chrome, or `NEXUS_TEST_PYTHON` to select the Python interpreter. Browser tests use `runtime/e2e.db`, never the live PostgreSQL database. CI runs these checks on Linux.

`python scripts/deploy.py verify` creates labelled simulation events and a reviewed simulation purchase order in the running PostgreSQL/Kafka environment, then verifies execution and replanning. The report is `runtime/artifacts/integration_verification.json`. It never contacts a supplier or spends money.

`python scripts/check_deployment.py` runs authenticated production browser checks with a temporary QA account removed in a finally block. `python scripts/check_recovery.py` intentionally stops this project's Kafka broker, proves retention and recovery, and restarts its worker. `python scripts/check_backup.py` restores the newest backup into a disposable database, checks its demand count, and removes that test database. Run fault injection only when an operator expects a brief interruption.

`requirements.lock.txt` records the tested Linux container package versions. `python scripts/package_release.py` packages active source, documentation, tests, and trained artifacts under `dist/` without secrets or raw datasets. On a new machine, follow the fresh-install dataset/bootstrap instructions; the ZIP is not a PostgreSQL or Kafka volume backup.
