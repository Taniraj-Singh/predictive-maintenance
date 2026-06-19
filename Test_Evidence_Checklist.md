# Test Evidence Checklist — Predictive Maintenance Platform

How to reproduce each piece of evidence. `BE=backend/`, run from `backend/`.

## Automated tests

| ID | Evidence | Command | Expected |
|----|----------|---------|----------|
| T-OPC-1..5 | OPC UA production scenarios | `python -m pytest app/tests/test_opcua_production.py -v` | 5 passed |
| T-ALARM | Auto critical alarm | `python -m pytest app/tests/test_services.py::test_alarm_created_on_high_value -v` | passed |
| T-ALL | Service-level suite | `python -m pytest app/tests/test_opcua_production.py app/tests/test_services.py -v` | 6 passed (2 SQLite-only failures noted in report) |

Prereqs (local, py3.13/3.14): `pip install -r requirements.txt` (or the subset
`sqlalchemy aiosqlite pydantic pydantic-settings loguru fastapi fpdf2 pyjwt passlib[bcrypt] httpx email-validator pytest pytest-asyncio`). `pytest.ini` sets `asyncio_mode=auto`.

## Runtime evidence (Docker stack up)

| ID | Acceptance item | Command | Expected |
|----|-----------------|---------|----------|
| R-HEALTH-1 | Liveness | `curl localhost:8000/health/live` | `{"status":"alive"}` |
| R-HEALTH-2 | Readiness | `curl localhost:8000/health/ready` | DB ok |
| R-HEALTH-3 | Status rollup | `curl localhost:8000/status` | backend/db/mqtt/ai states |
| R-DOCS | Swagger | open `localhost:8000/docs` | OpenAPI 3.1 UI |
| R-METRICS | Prometheus metrics | `curl localhost:8000/metrics` | metric lines incl. active alarms |
| R-AUTH-1 | Login | `POST /users/login` (form: username/password) | `access_token` |
| R-RBAC-1 | RBAC enforced — viewer cannot create machine | `POST /machines` with viewer token | `403` |
| R-RBAC-2 | RBAC enforced — unauth cannot create machine | `POST /machines` no token | `401` |
| R-MACH-1 | Create machine | `POST /machines` (engineer) | `201` + id |
| R-MACH-2 | Deactivate | `POST /machines/{id}/deactivate` | status `offline` |
| R-MACH-3 | Activate | `POST /machines/{id}/activate` | status `online` |
| R-MACH-4 | Status validation | `PATCH /machines/{id}` status=`bogus` | `422` |
| R-SENS-1 | Create sensor | `POST /sensors` (engineer) | `201` |
| R-SENS-2 | Sensor health | `GET /sensors/{id}/health` | `{online, last_seen, state}` |
| R-MQTT-1 | Ingestion flow | publish to `factory/...` topic | row in `sensor_data`, `last_seen` advances |
| R-MQTT-2 | Invalid payload rejected | publish non-JSON | warning logged, no row |
| R-OPC-1 | Test connection | `POST /opcua/test` | `ok:true` + sample_preview |
| R-OPC-2 | Activate + persist | `POST /opcua/activate` (engineer) | `persisted:true`; row in `opcua_source` |
| R-OPC-3 | Restart recovery | `docker compose restart backend` then `GET /opcua/status` | source still listed |
| R-AI-1 | AI status | `GET /ai/status` | model status |
| R-AI-2 | Retrain | `POST /ai/retrain` (admin) | job completed + model_version; new `model_registry` row |
| R-ALARM-1 | Flood protection | feed repeated threshold breaches | single active alarm |
| R-ALARM-2 | Offline detection | stop a sensor > threshold | offline alarm raised once |
| R-TICKET-1 | Auto ticket | trigger critical alarm | ticket linked to alarm+machine |
| R-REPORT-1 | Summary | `GET /reports/summary` | prediction_summary + alarm_summary |
| R-REPORT-2 | Generate | `POST /reports/generate {format:csv}` | downloadable CSV |
| R-DEPLOY-1 | Backup | `./scripts/backup.sh` | `pm_db_<ts>.sql.gz` |
| R-DEPLOY-2 | Restore | `./scripts/restore.sh <file>` | restore complete |
| R-SEC-1 | Prod-secrets guard | set `ENVIRONMENT=production`, default `JWT_SECRET` | backend refuses to start |

## Quick verification via Postman
Import `API_Test_Collection.json`, set `{{base_url}}`, run **Auth > Login**, then
the folders top-to-bottom. Token is captured automatically.
