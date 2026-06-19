# Architecture Report — Predictive Maintenance Platform

**Date:** 2026-06-19

## 1. System overview

A containerized, event-driven predictive-maintenance platform. Sensor telemetry
arrives via **MQTT** (and **OPC UA**), is persisted to **TimescaleDB/Postgres**,
scored by an **AI anomaly-detection service**, and surfaced through a **FastAPI**
backend to a **React** dashboard. Threshold/AI events auto-generate **alarms**,
which auto-generate **tickets**.

```
                         ┌────────────┐
   Field devices ─MQTT──▶│  mosquitto │──┐
   / Edge gateway        └────────────┘  │
                                         ▼
   OPC UA servers ─────────────▶ ┌───────────────┐   HTTP   ┌──────────────┐
                                 │  FastAPI       │─────────▶│ ai-service    │
                                 │  backend       │◀─────────│ (IsolationFor.)│
   React dashboard ◀─WS/SSE/REST─│                │  score   └──────────────┘
                                 │  consumer +    │
                                 │  opcua connector│──┐
                                 └───────────────┘  │ SQLAlchemy/asyncpg
                                                     ▼
                                            ┌──────────────────┐
                                            │ TimescaleDB/PG   │
                                            └──────────────────┘
```

## 2. Backend structure (`backend/app`)

| Layer | Path | Responsibility |
|-------|------|----------------|
| API routers | `api/routers/*` | HTTP endpoints, RBAC dependencies |
| Dependencies | `api/dependencies.py` | `get_current_user`, `require_admin/engineer/viewer` |
| Services | `services/*` | Business logic (machine, sensor, alarm, ticket, report, notification, webhook, prediction, audit) |
| Models | `models/*` | SQLAlchemy ORM (Base = UUID id + timestamps) |
| Schemas | `schemas/*` | Pydantic v2 request/response |
| Ingestion | `mqtt/consumer.py`, `opcua/` | MQTT consumer + OPC UA connector/registry/**repository** |
| Tasks | `tasks/*` | live-data generator, **offline-sensor monitor**, seed |
| Core | `core/config.py`, `core/security.py` | Settings (+ prod-secrets guard), JWT/bcrypt |
| Migrations | `alembic/versions/*` | Schema evolution (head: `0005`) |

## 3. Data model (key entities)

```
Machine 1───* Sensor 1───* SensorData
   │             │
   │             ├──* Prediction
   │             └──* Alarm ──1 Ticket
   │
   └──* Alarm/Prediction/Ticket (machine-scoped)

OPCUASource (persisted config + JSON node mappings)   ← restart recovery
User / Role / AuditLog / Webhook / Settings / Job / ModelRegistry
```

Notable fields added in this iteration:
- `Sensor.is_active`, `Sensor.last_seen` — health monitoring.
- `OPCUASource` table — durable OPC UA source/node mappings (migration `0005`).

## 4. Request & event flows

### Telemetry → alarm → ticket
1. `mqtt/consumer.py` receives & validates payload → `sensor_data_service.ingest_sensor_data` (updates `Sensor.last_seen`).
2. Calls `ai-service /predict`; persists `Prediction`.
3. On warning/critical → `alarm_service.is_alarm_suppressed` (flood gate) → `create_alarm`.
4. `ticket_service.ensure_ticket_for_alarm` → auto ticket linked to alarm+machine.
5. `realtime.broadcast_update` pushes WS/SSE to UI; webhooks fire for critical.

### OPC UA lifecycle
1. Wizard `POST /opcua/activate` → `repository.persist_source` (DB) → in-memory `registry`.
2. Connector polls nodes per `sampling_interval_ms`, normalizes via `schema_normalizer`.
3. On restart, `load_active_sources_into_registry()` rehydrates from DB.

### Offline detection
`tasks/offline_monitor.py` scans active sensors whose `last_seen` exceeds
`SENSOR_OFFLINE_AFTER_SECONDS` and raises a single (flood-protected) alarm.

## 5. Security architecture
- JWT bearer auth (HS256), refresh tokens, in-memory revoke list.
- RBAC via FastAPI dependencies; **all** machine/sensor writes require engineer+, deletes require admin.
- Secrets sourced from environment; production startup guard blocks insecure defaults.
- Input validation through Pydantic schemas + explicit status-enum validation.

## 6. Observability
- Structured logging (loguru) in backend & AI service.
- Prometheus `/metrics` (ingestion rate, prediction latency, active alarms, queue depth).
- Audit log for sensitive actions (`audit_service.log_action`).
- Distributed tracing (OpenTelemetry) is **not** implemented — see Production_Readiness_Report.md.

## 7. Deployment topology
Six Compose services on `pm-net`, Postgres-backed durable volume. Backend
container runs DB wait → alembic upgrade → uvicorn. Production variant in
`docker-compose.prod.yml`. Backup/restore via `scripts/`.

## 8. Technology stack
FastAPI · SQLAlchemy 2 (async) · Alembic · asyncpg · Pydantic v2 · paho-mqtt ·
asyncua · scikit-learn (IsolationForest/PCA) · React + Vite + TypeScript ·
TimescaleDB · Mosquitto · Docker Compose.
