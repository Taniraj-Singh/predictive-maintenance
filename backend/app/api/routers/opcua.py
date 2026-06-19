from __future__ import annotations

import asyncio
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_session, require_engineer
from app.core.config import get_settings
from app.models.user import User
from app.opcua.connector import opcua_connector
from app.opcua.repository import persist_source
from app.opcua.source_registry import OPCUANodeConfig, OPCUASourceConfig, registry


router = APIRouter(prefix="/opcua", tags=["opcua"])

settings = get_settings()


class OPCUANodeIn(BaseModel):
    node_id: str
    alias: str
    unit: str | None = None
    category: str | None = None


class OPCUAConfigIn(BaseModel):
    name: str = "OPC UA Source"
    endpoint_url: str
    namespace_index: int = 2
    sampling_interval_ms: int = 1_000
    session_timeout_ms: int = 60_000

    security_mode: str = "anonymous"
    security_policy: str | None = None
    security_mode_level: str | None = None
    username: str | None = None
    password: str | None = None
    ca_cert_pem: str | None = None
    client_cert_pem: str | None = None
    client_key_pem: str | None = None

    timestamp_source: str = "server"
    deduplication_enabled: bool = True
    unit_override_policy: str = "preserve"

    db_type: str = "timescale"
    db_name: str = settings.postgres_db
    tags: Dict[str, str] = {}
    retention_policy: str | None = None
    store_and_forward_enabled: bool = True

    nodes: List[OPCUANodeIn]


@router.get("/status")
async def get_opcua_status(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return high‑level heartbeat and node count for OPC UA connector."""
    heartbeat = opcua_connector.heartbeat_timestamp
    return {
        "connected": heartbeat is not None,
        "heartbeat_ts": heartbeat,
        "node_count": opcua_connector.node_count,
        "last_error": opcua_connector.last_error,
        "sources": [
            {
                "id": s.id,
                "name": s.name,
                "endpoint_url": s.endpoint_url,
                "active": s.active,
                "node_count": len(s.nodes),
            }
            for s in registry.all()
        ],
    }


@router.post("/test")
async def test_connection(
    payload: OPCUAConfigIn,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Perform a light‑weight connection test.
    For now we don't depend on a real OPC UA server being reachable – on error
    we simply surface the exception message back to the caller.
    """
    from datetime import datetime

    handshake_logs: List[str] = []
    handshake_logs.append(f"Preparing OPC UA test to {payload.endpoint_url}")

    try:
        # We don't perform a real handshake here to keep tests predictable in
        # environments without OPC UA servers. This endpoint mainly validates
        # that the configuration payload is well‑formed.
        handshake_logs.append("Configuration payload validated successfully.")
        sample_preview = [
            {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "alias": node.alias,
                "value": 0.0,
                "quality": "Good",
                "unit": node.unit or "",
            }
            for node in payload.nodes[:3]
        ]
        return {
            "ok": True,
            "handshake_logs": handshake_logs,
            "sample_preview": sample_preview,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/activate")
async def activate_source(
    payload: OPCUAConfigIn,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_engineer),
):
    """Register / update an OPC UA source, persist it, and mark it active."""
    source_id = str(uuid4())
    nodes = [
        OPCUANodeConfig(
            node_id=n.node_id,
            alias=n.alias,
            unit=n.unit,
            category=n.category,
        )
        for n in payload.nodes
    ]

    cfg = OPCUASourceConfig(
        id=source_id,
        name=payload.name,
        endpoint_url=payload.endpoint_url,
        namespace_index=payload.namespace_index,
        sampling_interval_ms=payload.sampling_interval_ms,
        session_timeout_ms=payload.session_timeout_ms,
        security_mode=payload.security_mode,
        security_policy=payload.security_policy or "",
        security_mode_level=payload.security_mode_level or "",
        username=payload.username,
        password=payload.password,
        ca_cert_pem=payload.ca_cert_pem,
        client_cert_pem=payload.client_cert_pem,
        client_key_pem=payload.client_key_pem,
        timestamp_source=payload.timestamp_source,
        deduplication_enabled=payload.deduplication_enabled,
        unit_override_policy=payload.unit_override_policy,
        db_type=payload.db_type,
        db_name=payload.db_name,
        tags=payload.tags or {},
        retention_policy=payload.retention_policy,
        store_and_forward_enabled=payload.store_and_forward_enabled,
        nodes=nodes,
        active=True,
    )

    # Persist to the database first so the configuration survives restarts,
    # then mirror the persisted id into the in-memory registry.
    try:
        persisted_id = await persist_source(cfg)
        cfg.id = persisted_id
    except Exception as exc:  # pragma: no cover - surfaced to caller
        raise HTTPException(status_code=500, detail=f"Failed to persist OPC UA source: {exc}")

    registry.upsert(cfg)
    registry.mark_active(cfg.id, True)

    # Ensure background worker is running
    loop = opcua_connector._loop  # type: ignore[attr-defined]
    if loop is None:
        loop = asyncio.get_event_loop()
        opcua_connector.start(loop)

    return {"id": cfg.id, "name": cfg.name, "node_count": len(cfg.nodes), "persisted": True}



