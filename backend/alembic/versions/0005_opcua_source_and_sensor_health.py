"""Add opcua_source table and sensor health columns (is_active, last_seen)

Revision ID: 0005_opcua_source_and_sensor_health
Revises: 0004_add_idempotency_key_to_sensor_data
Create Date: 2026-06-19
"""

from alembic import op


revision = "0005_opcua_source_and_sensor_health"
down_revision = "0004_add_idempotency_key_to_sensor_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Sensor health monitoring columns
    op.execute(
        "ALTER TABLE sensor ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE"
    )
    op.execute(
        "ALTER TABLE sensor ADD COLUMN IF NOT EXISTS last_seen TIMESTAMPTZ NULL"
    )

    # Persistent OPC UA source configuration (restart recovery)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS opcua_source (
            id UUID PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            name VARCHAR(255) NOT NULL DEFAULT 'OPC UA Source',
            endpoint_url VARCHAR(512) NOT NULL,
            namespace_index INTEGER NOT NULL DEFAULT 2,
            sampling_interval_ms INTEGER NOT NULL DEFAULT 1000,
            session_timeout_ms INTEGER NOT NULL DEFAULT 60000,
            security_mode VARCHAR(32) NOT NULL DEFAULT 'anonymous',
            security_policy VARCHAR(128) NULL,
            security_mode_level VARCHAR(64) NULL,
            username VARCHAR(255) NULL,
            password TEXT NULL,
            ca_cert_pem TEXT NULL,
            client_cert_pem TEXT NULL,
            client_key_pem TEXT NULL,
            timestamp_source VARCHAR(32) NOT NULL DEFAULT 'server',
            deduplication_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            unit_override_policy VARCHAR(32) NOT NULL DEFAULT 'preserve',
            db_type VARCHAR(32) NOT NULL DEFAULT 'timescale',
            db_name VARCHAR(128) NULL,
            tags JSON NULL,
            retention_policy VARCHAR(64) NULL,
            store_and_forward_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            nodes JSON NOT NULL DEFAULT '[]',
            active BOOLEAN NOT NULL DEFAULT FALSE
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_opcua_source_active ON opcua_source(active)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_opcua_source_active")
    op.execute("DROP TABLE IF EXISTS opcua_source")
    op.execute("ALTER TABLE sensor DROP COLUMN IF EXISTS last_seen")
    op.execute("ALTER TABLE sensor DROP COLUMN IF EXISTS is_active")
