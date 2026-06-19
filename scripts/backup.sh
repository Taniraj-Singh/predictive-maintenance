#!/usr/bin/env bash
#
# Database backup for the Predictive Maintenance Platform.
# Creates a compressed pg_dump of the Postgres/TimescaleDB instance running in
# the `postgres` compose service.
#
# Usage:
#   ./scripts/backup.sh [output_dir]
#
# Env (with defaults matching docker-compose):
#   POSTGRES_USER (pm_user)  POSTGRES_DB (pm_db)  COMPOSE_FILE (docker-compose.yml)
#
set -euo pipefail

OUT_DIR="${1:-./backups}"
POSTGRES_USER="${POSTGRES_USER:-pm_user}"
POSTGRES_DB="${POSTGRES_DB:-pm_db}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

mkdir -p "$OUT_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="${OUT_DIR}/pm_db_${TS}.sql.gz"

echo "▶ Backing up database '${POSTGRES_DB}' to ${OUT_FILE}"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists \
    | gzip > "$OUT_FILE"

echo "✅ Backup complete: ${OUT_FILE} ($(du -h "$OUT_FILE" | cut -f1))"

# Retain only the 14 most recent backups
ls -1t "${OUT_DIR}"/pm_db_*.sql.gz 2>/dev/null | tail -n +15 | xargs -r rm -f
echo "🧹 Old backups pruned (kept newest 14)."
