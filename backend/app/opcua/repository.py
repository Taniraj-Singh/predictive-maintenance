"""Persistence bridge between the OPC UA DB model and the in-memory registry.

The connector reads source configs from the in-memory `registry` for speed.
This module keeps that registry durable: it writes through to the
`opcua_source` table on activate, and reloads active sources on startup so
mappings survive restarts (restart recovery).
"""
from __future__ import annotations

from typing import List

from loguru import logger
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.opcua_source import OPCUASource
from app.opcua.source_registry import OPCUANodeConfig, OPCUASourceConfig, registry


def _config_from_row(row: OPCUASource) -> OPCUASourceConfig:
    nodes = [
        OPCUANodeConfig(
            node_id=n.get("node_id", ""),
            alias=n.get("alias", ""),
            unit=n.get("unit"),
            category=n.get("category"),
        )
        for n in (row.nodes or [])
    ]
    return OPCUASourceConfig(
        id=str(row.id),
        name=row.name,
        endpoint_url=row.endpoint_url,
        namespace_index=row.namespace_index,
        sampling_interval_ms=row.sampling_interval_ms,
        session_timeout_ms=row.session_timeout_ms,
        security_mode=row.security_mode,
        security_policy=row.security_policy or "",
        security_mode_level=row.security_mode_level or "",
        username=row.username,
        password=row.password,
        ca_cert_pem=row.ca_cert_pem,
        client_cert_pem=row.client_cert_pem,
        client_key_pem=row.client_key_pem,
        timestamp_source=row.timestamp_source,
        deduplication_enabled=row.deduplication_enabled,
        unit_override_policy=row.unit_override_policy,
        db_type=row.db_type,
        db_name=row.db_name,
        tags=row.tags or {},
        retention_policy=row.retention_policy,
        store_and_forward_enabled=row.store_and_forward_enabled,
        nodes=nodes,
        active=row.active,
    )


def _nodes_to_json(cfg: OPCUASourceConfig) -> list:
    return [
        {"node_id": n.node_id, "alias": n.alias, "unit": n.unit, "category": n.category}
        for n in cfg.nodes
    ]


async def persist_source(cfg: OPCUASourceConfig) -> str:
    """Insert (or update) a source row and return its persisted id (string)."""
    async with AsyncSessionLocal() as session:
        row: OPCUASource | None = None
        # Try to update an existing row when the registry id matches a DB id.
        try:
            row = await session.get(OPCUASource, cfg.id)
        except Exception:
            row = None

        if row is None:
            row = OPCUASource()
            session.add(row)

        row.name = cfg.name
        row.endpoint_url = cfg.endpoint_url
        row.namespace_index = cfg.namespace_index
        row.sampling_interval_ms = cfg.sampling_interval_ms
        row.session_timeout_ms = cfg.session_timeout_ms
        row.security_mode = cfg.security_mode
        row.security_policy = cfg.security_policy
        row.security_mode_level = cfg.security_mode_level
        row.username = cfg.username
        row.password = cfg.password
        row.ca_cert_pem = cfg.ca_cert_pem
        row.client_cert_pem = cfg.client_cert_pem
        row.client_key_pem = cfg.client_key_pem
        row.timestamp_source = cfg.timestamp_source
        row.deduplication_enabled = cfg.deduplication_enabled
        row.unit_override_policy = cfg.unit_override_policy
        row.db_type = cfg.db_type
        row.db_name = cfg.db_name
        row.tags = cfg.tags
        row.retention_policy = cfg.retention_policy
        row.store_and_forward_enabled = cfg.store_and_forward_enabled
        row.nodes = _nodes_to_json(cfg)
        row.active = cfg.active

        await session.commit()
        await session.refresh(row)
        return str(row.id)


async def load_active_sources_into_registry() -> int:
    """Reload persisted active sources into the in-memory registry at startup."""
    count = 0
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(OPCUASource).where(OPCUASource.active.is_(True))
            )
            rows: List[OPCUASource] = list(result.scalars().all())
        for row in rows:
            registry.upsert(_config_from_row(row))
            count += 1
        if count:
            logger.info("Restored {} OPC UA source(s) from database", count)
    except Exception as e:  # pragma: no cover - non-fatal at startup
        logger.warning("Could not restore OPC UA sources (table may not exist yet): {}", e)
    return count
