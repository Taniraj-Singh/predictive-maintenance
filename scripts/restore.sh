#!/usr/bin/env bash
#
# Restore the Predictive Maintenance database from a backup produced by
# scripts/backup.sh (gzipped pg_dump).
#
# Usage:
#   ./scripts/restore.sh ./backups/pm_db_20260619_120000.sql.gz
#
# WARNING: this overwrites the current database contents.
#
set -euo pipefail

BACKUP_FILE="${1:-}"
POSTGRES_USER="${POSTGRES_USER:-pm_user}"
POSTGRES_DB="${POSTGRES_DB:-pm_db}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

if [[ -z "$BACKUP_FILE" || ! -f "$BACKUP_FILE" ]]; then
    echo "Usage: $0 <backup_file.sql.gz>" >&2
    exit 1
fi

echo "⚠  This will OVERWRITE database '${POSTGRES_DB}'."
read -r -p "Type the database name to confirm: " CONFIRM
if [[ "$CONFIRM" != "$POSTGRES_DB" ]]; then
    echo "Aborted." >&2
    exit 1
fi

echo "▶ Restoring '${POSTGRES_DB}' from ${BACKUP_FILE}"
gunzip -c "$BACKUP_FILE" | docker compose -f "$COMPOSE_FILE" exec -T postgres \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"

echo "✅ Restore complete."
