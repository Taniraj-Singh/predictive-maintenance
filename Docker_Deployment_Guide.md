# Docker Deployment Guide — Predictive Maintenance Platform

## 1. Architecture (services)

| Service     | Image / Build        | Port (host:container) | Purpose |
|-------------|----------------------|-----------------------|---------|
| `postgres`  | timescale/timescaledb:latest-pg15 | 5432:5432 | Time-series + relational store |
| `mqtt`      | eclipse-mosquitto:2  | 1883:1883 | MQTT broker |
| `ai-service`| build `./ai_service` | 8001:8000 | Anomaly-detection inference |
| `backend`   | build `./backend`    | 8000:8000 | FastAPI API, MQTT/OPC UA ingestion |
| `frontend`  | build `./frontend`   | 3000:80  | React dashboard (nginx) |
| `simulator` | build `./simulator`  | —        | Edge data generator |

Network: `pm-net` (bridge). Volume: `postgres-data` (DB persistence).

## 2. Prerequisites

- Docker Engine 24+ and Docker Compose v2 (`docker compose version`)
- 4 GB RAM minimum

## 3. Configuration

```bash
cp .env.example .env
# Edit .env and set, at minimum:
#   ENVIRONMENT=production
#   POSTGRES_PASSWORD=<strong value>
#   JWT_SECRET=$(openssl rand -hex 32)
```

> **Security gate:** when `ENVIRONMENT` is not `local`/`dev`/`test`, the backend
> refuses to start if `JWT_SECRET` or `POSTGRES_PASSWORD` are left at their
> insecure defaults (see `app/core/config.py:validate_production_secrets`).

Email/Slack notifications are optional and disabled unless
`EMAIL_SMTP_USER` / `EMAIL_SMTP_PASS` / `NOTIFICATION_EMAIL` (and/or
`SLACK_WEBHOOK_URL`) are provided.

## 4. Bring up the stack

```bash
docker compose up -d --build
docker compose ps                 # all services healthy
docker compose logs -f backend    # watch startup + migrations
```

Startup sequence performed automatically by the backend container:
1. `scripts/wait_for_db.py` — waits for Postgres.
2. `scripts/fix_alembic_version.py` — reconciles legacy alembic state (best-effort).
3. `alembic upgrade head` — applies migrations (incl. `0005` opcua_source + sensor health).
4. `uvicorn app.main:app` — starts API; restores persisted OPC UA sources; seeds demo users/machines; starts MQTT consumer, live-data + offline-sensor monitors.

## 5. Verify

```bash
curl http://localhost:8000/health/live          # {"status":"alive"}
curl http://localhost:8000/health/ready          # DB readiness
curl http://localhost:8000/status                # backend/db/mqtt/ai rollup
open  http://localhost:8000/docs                 # Swagger UI
open  http://localhost:3000                      # Dashboard
```

Default seeded logins (change immediately in production): `admin`, `engineer`,
`viewer` — see `app/tasks/seed_demo_data.py`.

## 6. Database migrations

```bash
docker compose exec backend alembic upgrade head     # apply
docker compose exec backend alembic downgrade -1     # roll back one
docker compose exec backend alembic history          # list
```

## 7. Backup & restore

```bash
./scripts/backup.sh ./backups                       # creates pm_db_<ts>.sql.gz, keeps newest 14
./scripts/restore.sh ./backups/pm_db_<ts>.sql.gz    # restores (prompts for confirmation)
```

Schedule daily backups with cron:
```
0 2 * * * cd /opt/pm && ./scripts/backup.sh /var/backups/pm >> /var/log/pm-backup.log 2>&1
```

## 8. Production compose

`docker-compose.prod.yml` is provided for production (reverse proxy / TLS,
restart policies). Use:
```bash
docker compose -f docker-compose.prod.yml up -d --build
```

## 9. Tests

```bash
docker compose exec backend python -m pytest app/tests -v
# OPC UA production scenarios:
docker compose exec backend python -m pytest app/tests/test_opcua_production.py -v
```

## 10. Teardown

```bash
docker compose down            # stop, keep data volume
docker compose down -v         # stop and DELETE the database volume
```
