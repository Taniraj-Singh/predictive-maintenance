# Phase 1 — Gap Analysis Matrix

**Project:** Predictive Maintenance Platform
**Audit date:** 2026-06-19
**Method:** Static code audit of backend (FastAPI/SQLAlchemy/Alembic), AI service, MQTT consumer, OPC UA connector, React frontend, Docker stack. Four parallel subsystem audits cross-checked against the acceptance checklist, then key findings re-verified by direct file reads.

Legend — **Status:** ✅ Implemented · 🟡 Partial · ❌ Missing · 🔴 Broken

| # | Requirement | Current Status | Pass/Fail | Missing Components | Implementation Plan |
|---|-------------|----------------|-----------|--------------------|---------------------|
| **1** | **System Health** | | | | |
| 1.1 | Docker Compose | ✅ valid 6-service stack (`docker-compose.yml`) | PASS | — | — |
| 1.2 | Health Endpoints | ✅ `/health`, `/health/live`, `/health/ready` (`routers/health.py`) | PASS | — | — |
| 1.3 | Status Endpoint | ✅ `/status` checks DB/MQTT/AI (`routers/health.py:62`) | PASS | — | — |
| 1.4 | API Docs | ✅ Swagger `/docs`, ReDoc, OpenAPI 3.1 (`main.py:48`) | PASS | — | — |
| 1.5 | Service Monitoring | ✅ `/metrics` + frontend `ServiceStatusCard` | PASS | — | — |
| **2** | **Authentication & RBAC** | | | | |
| 2.1 | JWT Authentication | ✅ create/verify/refresh/blacklist (`core/security.py`) | PASS | — | — |
| 2.2 | Admin/Engineer/Viewer Roles | ✅ defined & seeded (`dependencies.py:59`, `seed_demo_data.py`) | PASS | — | — |
| 2.3 | Permission Enforcement | 🔴 **machines & sensors write endpoints had NO auth at all** | **FAIL** | `require_engineer`/`get_current_user` on write routes | Add role deps to all POST/PATCH/DELETE |
| 2.4 | User Management | 🟡 no admin list-users / activate / delete endpoints | FAIL | `GET /users`, deactivate, role-change | Add admin user-management endpoints |
| 2.5 | Password Hashing | ✅ bcrypt via passlib (`core/security.py`) | PASS | — | — |
| **3** | **Machine Management** | | | | |
| 3.1 | CRUD Operations | ✅ full CRUD + bulk (`routers/machines.py`) | PASS | — | — |
| 3.2 | Machine Activation | ❌ no explicit endpoint; status free-text, unvalidated | FAIL | `POST /machines/{id}/activate`, status validation | Add endpoints + enum validation |
| 3.3 | Machine Deactivation | ❌ same | FAIL | `POST /machines/{id}/deactivate` | Add endpoint with audit log |
| **4** | **Sensor Management** | | | | |
| 4.1 | CRUD Operations | ✅ full CRUD (`routers/sensors.py`) | PASS | — | — |
| 4.2 | Sensor-Machine Mapping | ✅ FK + cascade + filter (`models/sensor.py:8`) | PASS | — | — |
| 4.3 | Sensor Health Monitoring | 🟡 trend stats only; no `is_active`/`last_seen` | FAIL | health fields + offline detection | Add fields + scheduled job |
| **5** | **MQTT Ingestion** | | | | |
| 5.1 | Broker Connectivity | ✅ auto-reconnect (`mqtt/consumer.py`) | PASS | — | — |
| 5.2 | Topic Configuration | ✅ wildcards + QoS1 + env override | PASS | — | — |
| 5.3 | Payload Validation | ✅ required-field + numeric coercion | PASS | — | — |
| 5.4 | Invalid Payload Rejection | ✅ JSONDecode + missing-field guards | PASS | — | — |
| 5.5 | Real-time Flow MQTT→BE→DB→UI | ✅ queue→DB→WS/SSE broadcast | PASS | — | — |
| **6** | **OPC UA Integration** | | | | |
| 6.1 | OPC UA Wizard | ✅ 6-step wizard (`OPCUAWizard.tsx`) | PASS | — | — |
| 6.2 | Endpoint Testing | 🟡 mock test, no real handshake | PARTIAL | optional real handshake | Keep mock; add real connect path |
| 6.3 | Node Browsing | 🟡 manual node entry only | PARTIAL | live browse | Document as manual; optional later |
| 6.4 | Sensor Mapping | ✅ node→sensor auto-create (`connector.py:182`) | PASS | — | — |
| 6.5 | Sampling Configuration | ✅ per-source interval honored | PASS | — | — |
| 6.6 | Live Preview | ✅ normalized sample preview | PASS | — | — |
| 6.7 | Persistent Mapping | 🔴 **in-memory dict only** (`source_registry.py:61`) | **FAIL** | DB model + migration + repo | Persist sources/nodes to DB |
| 6.8 | Restart Recovery | 🔴 **all config lost on restart** | **FAIL** | load-on-startup | Reload active sources at startup |
| **7** | **AI Prediction Engine** | | | | |
| 7.1 | Real Data Inference | ✅ IsolationForest + rules (`ai_service/main.py`) | PASS | — | — |
| 7.2 | Prediction Scores | ✅ score 0–1 | PASS | — | — |
| 7.3 | Confidence Scores | ✅ `_calculate_confidence` | PASS | — | — |
| 7.4 | Normal/Warning/Critical | ✅ thresholded classification | PASS | — | — |
| 7.5 | Retraining Support | 🟡 `/ai/retrain` is a stub (job id only) | FAIL | real trigger | Run training job in background task |
| 7.6 | Model Version Tracking | ✅ `model_registry` + metadata.json | PASS | activate/rollback are stubs | Wire activation |
| **8** | **Alarm System** | | | | |
| 8.1 | Auto Alarm Creation | ✅ from threshold + prediction | PASS | — | — |
| 8.2 | Severity Levels | ✅ info/warning/critical | PASS | — | — |
| 8.3 | Flood Protection | 🔴 **none — alarm per reading** (`alarm_service.py`) | **FAIL** | state-change dedup | Suppress if open alarm exists in window |
| 8.4 | Offline Sensor Detection | ❌ no heartbeat/last_seen | FAIL | last_seen + monitor job | Add scheduled offline scan |
| **9** | **Automatic Ticket Workflow** | | | | |
| 9.1 | Auto Ticket Creation | ✅ `ensure_ticket_for_alarm` | PASS | — | — |
| 9.2 | Alarm Linking | ✅ `ticket.alarm_id` | PASS | — | — |
| 9.3 | Machine Linking | ✅ `ticket.machine_id` | PASS | — | — |
| 9.4 | Lifecycle Tracking | ✅ status enum + comments | PASS | — | — |
| **10** | **Reporting** | | | | |
| 10.1 | Report Generation | ✅ CSV/PDF (`report_service.py`) | PASS | — | — |
| 10.2 | Prediction Summary | 🟡 sensor rows only | PARTIAL | prediction aggregation | Add prediction summary section |
| 10.3 | Alarm Summary | ❌ not in reports | FAIL | alarm aggregation | Add alarm summary section |
| **11** | **Notifications & Webhooks** | ✅ email/Slack/webhook CRUD + triggers | PASS | hardcoded recipient | Make recipient configurable |
| **12** | **Logging & Observability** | | | | |
| 12.1 | Structured Logging | ✅ loguru | PASS | central config | Add log config module |
| 12.2 | Metrics | ✅ Prometheus `/metrics` | PASS | — | — |
| 12.3 | Tracing | ❌ no OpenTelemetry | FAIL (optional) | OTel | Documented as optional/out-of-scope |
| **13** | **Deployment** | | | | |
| 13.1 | Docker | ✅ all 4 Dockerfiles | PASS | — | — |
| 13.2 | Backup | ❌ no script | FAIL | `backup.sh` | Add pg_dump script |
| 13.3 | Restore | ❌ no script | FAIL | `restore.sh` | Add psql restore script |
| 13.4 | Environment Variables | 🔴 **hardcoded SMTP password in `config.py:60`** | **FAIL** | secret removal | Move to env, no insecure default |
| **14** | **OPC UA Production Tests** | | | | |
| 14.1–14.5 | Connection / Normal / Drift / Fault / Recovery | ❌ none exist | FAIL | pytest suite + simulator | Add 5-scenario test suite |

## Critical (must-fix) summary

1. 🔴 **RBAC not enforced** on machine/sensor writes — any unauthenticated caller could mutate assets.
2. 🔴 **Hardcoded SMTP password** committed in `config.py`.
3. 🔴 **OPC UA config not persisted** — lost on every restart.
4. 🔴 **No alarm flood protection** — stable industrial signals cause alarm storms.
5. ❌ Missing: machine activate/deactivate, offline sensor detection, alarm-summary reports, backup/restore, OPC UA production tests.

All of the above are addressed in Phase 2 below.
