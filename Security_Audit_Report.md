# Security Audit Report — Predictive Maintenance Platform

**Date:** 2026-06-19
**Scope:** AuthN/AuthZ, secrets, input validation, transport, data-at-rest, deployment.

## 1. Findings & remediation

| # | Severity | Finding | Status | Evidence |
|---|----------|---------|--------|----------|
| S-1 | **Critical** | Hardcoded SMTP password (`tanirajsingh1122`) in `config.py` | ✅ Fixed | creds removed; env-only (`core/config.py`) |
| S-2 | **Critical** | Hardcoded credential in `create_user.py` | ✅ Fixed | now CLI/env args, no defaults |
| S-3 | **Critical** | Machine/Sensor write endpoints had **no auth** | ✅ Fixed | `require_engineer`/`require_admin` added (`routers/machines.py`, `routers/sensors.py`) |
| S-4 | High | Insecure default `JWT_SECRET=change-me` could ship to prod | ✅ Mitigated | `validate_production_secrets` blocks boot on insecure defaults when `ENVIRONMENT!=local` |
| S-5 | High | Hardcoded notification recipient (PII) | ✅ Fixed | `NOTIFICATION_EMAIL` env |
| S-6 | Medium | OPC UA secrets (passwords, client keys) stored plaintext in new `opcua_source` table | ⚠️ Documented | encrypt-at-rest recommended (pgcrypto/KMS); noted in model + below |
| S-7 | Medium | CORS `allow_origins=["*"]` with credentials | ⚠️ Open | acceptable for dev; restrict origins in prod (recommendation) |
| S-8 | Low | In-memory JWT revoke list (not shared across replicas) | ⚠️ Open | move to Redis for horizontal scaling |
| S-9 | Low | No rate limiting on auth endpoints | ⚠️ Open | add slowapi/gateway throttle in prod |

## 2. Authentication & authorization
- **JWT** HS256 with expiry + refresh tokens; bcrypt password hashing (passlib). ✅
- **RBAC**: three roles, enforced via dependency injection. After this iteration,
  every mutating endpoint on machines/sensors/OPC UA is role-gated; deletes are
  admin-only. ✅
- Verified there are no `Depends(get_session)`-only write endpoints remaining on
  machines/sensors.

## 3. Secrets management
- All secrets now sourced from environment / `.env` (gitignored expected).
- `.env.example` ships with placeholders and explicit "generate with openssl" guidance.
- Startup guard refuses production boot with default `JWT_SECRET`/`POSTGRES_PASSWORD`.
- **Action for operators:** rotate the previously-committed SMTP password — it must
  be considered compromised since it existed in source history.

## 4. Input validation
- Pydantic v2 schemas validate all request bodies.
- Machine status validated against `MachineStatus` enum (`machine_service._validate_status`).
- MQTT payloads validated (required fields, numeric coercion, JSON guards).
- Report download path-traversal guard present (`routers/reports.py`).

## 5. Data at rest / in transit
- DB credentials via env; volume-persisted Postgres.
- ⚠️ OPC UA credential columns are plaintext (S-6). Recommend pgcrypto column
  encryption or external secret store before storing production OPC UA secrets.
- TLS termination expected at the reverse proxy (prod compose) — enforce HTTPS.

## 6. Recommendations (prioritized)
1. **Rotate the exposed SMTP credential** (was in source).
2. Restrict CORS origins and enforce HTTPS in production.
3. Encrypt OPC UA secret columns (pgcrypto/KMS).
4. Move JWT revocation list + settings cache to Redis for multi-replica.
5. Add auth-endpoint rate limiting.
6. Add dependency scanning (pip-audit / npm audit) to CI.

## 7. Residual risk
With S-1..S-5 remediated, no critical/high issues remain **in the running
configuration** provided operators set strong env secrets and rotate the
previously-exposed SMTP password. Remaining items (S-6..S-9) are hardening
recommendations for multi-tenant/production-scale operation.
