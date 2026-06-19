# Cleanup Report — Predictive Maintenance Platform

**Date:** 2026-06-19
**Principle:** Nothing was deleted without first verifying it is unreferenced by
code, Docker Compose, Dockerfiles, or the canonical README/deploy docs
(`grep` evidence retained below).

## 1. Removed files (24)

### Transient "fix note" documents (root) — superseded, not referenced
| File | Reason |
|------|--------|
| FIX_ALEMBIC_COLUMN.md | One-off troubleshooting note (alembic column width) |
| FIX_ALEMBIC_MANUAL.md | One-off troubleshooting note |
| FIX_API_DOCS.md | One-off troubleshooting note (OpenAPI version) |
| FIX_BACKEND_CONNECTION.md | One-off troubleshooting note |
| FIX_DATABASE_TABLES.md | One-off troubleshooting note |
| FIX_LIVE_UPDATES.md | One-off troubleshooting note |
| FIX_OFFLINE_MODE.md | One-off troubleshooting note |
| FIX_PORT_80.txt | One-off troubleshooting note |
| QUICK_FIX_PORT.md | Duplicate of port guidance |
| REBUILD_FRONTEND_FIX.md | One-off troubleshooting note |
| RUN_ON_DIFFERENT_PORT.md | Superseded by deployment guide |
| COMPLETE_FIX_GUIDE.md | Aggregated transient fixes |
| FIXES_AND_IMPROVEMENTS.md | Changelog-style scratch notes |
| VERIFY_BACKEND_FIX.md | One-off verification note |
| TODAY_WORK_LIST.md | Personal TODO scratch file |
| TEST_RESULTS.md | Stale manual test snapshot |

### One-off fix scripts — task completed, logic now upstream
| File | Reason |
|------|--------|
| apply-api-docs-fix.ps1 | OpenAPI fix already applied in `main.py` |
| apply-api-docs-fix.sh | duplicate of the above |

### Redundant deploy quick-notes — consolidated into `NETCUP_DEPLOYMENT.md` + new `Docker_Deployment_Guide.md`
| File | Reason |
|------|--------|
| QUICK_DEPLOY_NETCUP.txt | Subset of NETCUP_DEPLOYMENT.md |
| NETCUP_DEPLOY_COMMANDS.txt | Subset of NETCUP_DEPLOYMENT.md |

### Dead / fake / demo code — unreferenced (verified by grep)
| File | Reason |
|------|--------|
| backend/quick_gen_predictions.py | Fake prediction generator; not imported anywhere, not in production path |
| backend/scripts/generate_fake_predictions.py | Fake prediction generator; only self-references |
| ai_service/mqtt_quick_fix.py | Ad-hoc MQTT connection probe; not imported by `main.py` |
| ai_service/test_mqtt.py | Ad-hoc script (not a pytest test); unreferenced |

## 2. Code-level cleanups (refactors, not deletions)

| Change | File | Reason |
|--------|------|--------|
| Removed hardcoded SMTP password & email | `backend/app/core/config.py` | Secret in source control (critical) |
| Removed hardcoded recipient `tanirajsingh574@gmail.com` | `notification_service.py` | Hardcoded PII recipient → env `NOTIFICATION_EMAIL` |
| Removed hardcoded credentials in `create_user.py` | `backend/create_user.py` | Replaced with CLI/env-driven args |
| Fixed dead `Alarm.status == "active"` queries (×5) | dashboard/metrics/realtime/machines routers | Alarms never have status "active" → counts were always 0 |
| Fixed broken indentation / missing import paths | `mqtt/consumer.py` | Correctness while adding flood protection |

## 3. Verification commands used

```bash
# Fake-data / quick-fix scripts unreferenced in code & config:
grep -rniE "quick_gen_predictions|generate_fake_predictions|mqtt_quick_fix|test_mqtt" \
  --include="*.py" --include="*.yml" --include="Dockerfile" .
# (only self-references found)

# Fix-note docs not referenced by README/compose/Dockerfiles:
grep -rniE "FIX_ALEMBIC|FIX_API_DOCS|...|apply-api-docs" README.md docker-compose*.yml
# (only scripts/fix_alembic_version.py — a DIFFERENT, KEPT file — matched)
```

## 4. Deliberately KEPT (verified still in use)

| File | Why kept |
|------|----------|
| backend/scripts/fix_alembic_version.py | Invoked by `docker-compose.yml` startup command |
| backend/scripts/wait_for_db.py | Invoked by startup command |
| backend/test_production.py | Manual production smoke-test harness (useful) |
| ai_service/mqtt_enterprise_simulator.py, mqtt_enterprise_bridge.py, mqtt_publisher.py | Simulation/bridge tooling referenced by HOW_TO_RUN_SIMULATOR.md |
| simulator/ (edge_gateway_sim.py, publish_sim.py) | Wired as the `simulator` compose service |

## 5. Remaining doc-consolidation opportunities (not deleted — low risk, owner's call)

The following overlap and could be merged later, but were **kept** to avoid
removing potentially-referenced onboarding docs without owner sign-off:
`QUICK_START.md`, `DEPLOYMENT_QUICK_START.md`, `STEP_BY_STEP_DEPLOY.md`,
`NETCUP_DEPLOYMENT.md`. The new `Docker_Deployment_Guide.md` is the canonical
deployment reference going forward.

## 6. Net effect
- 24 files removed (≈ all transient/dead).
- 0 production code paths affected (all removed files were unreferenced).
- Repository root reduced from ~40 loose docs/scripts to a focused set.
