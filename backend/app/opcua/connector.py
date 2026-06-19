from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from loguru import logger

from app.core.config import Settings, get_settings
from app.db.session import AsyncSessionLocal
from app.opcua.schema_normalizer import normalize_opcua_sample
from app.opcua.source_registry import OPCUASourceConfig, registry
from app.services import sensor_data_service, sensor_service, machine_service, alarm_service

try:
    # asyncua is a popular async OPC UA client library
    from asyncua import Client, ua
except Exception:  # pragma: no cover - optional dependency
    Client = None  # type: ignore
    ua = None  # type: ignore


class OPCUAConnector:
    """
    Long‑running worker that establishes OPC UA sessions and subscribes to
    configured nodes. It mirrors the behaviour of the MQTTIngestor but for
    OPC UA subscriptions.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._heartbeat_ts: Optional[float] = None
        self._last_error: Optional[str] = None
        self._active_nodes_count: int = 0

    # Public status ---------------------------------------------------------
    @property
    def heartbeat_timestamp(self) -> Optional[float]:
        return self._heartbeat_ts

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    @property
    def node_count(self) -> int:
        return self._active_nodes_count

    # Lifecycle -------------------------------------------------------------
    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._running:
            return
        self._loop = loop
        self._running = True
        self._task = loop.create_task(self._run(), name="opcua-connector")
        logger.info("OPC UA connector worker started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("OPC UA connector worker stopped")

    # Core worker loop ------------------------------------------------------
    async def _run(self) -> None:
        """
        Iterate over all active sources in the registry and ensure there is an
        active subscription for each. If asyncua is not installed we still keep
        the worker alive and simply log a warning – this avoids breaking the
        rest of the stack.
        """
        if Client is None:
            logger.warning(
                "asyncua library is not installed – OPC UA connector will run in "
                "no‑op mode. Install 'asyncua' to enable real OPC UA ingestion."
            )

        while self._running:
            try:
                active_sources = [s for s in registry.all() if s.active]
                self._active_nodes_count = sum(len(s.nodes) for s in active_sources)
                self._heartbeat_ts = asyncio.get_event_loop().time()

                # For now we keep a simple sequential loop; each iteration
                # re‑creates short‑lived sessions to pull a sample from every
                # configured node. This keeps the implementation lightweight
                # while still honouring sampling_interval_ms.
                for source in active_sources:
                    await self._poll_source_once(source)

                # Sleep for the minimum configured sampling interval
                if active_sources:
                    min_interval_ms = min(s.sampling_interval_ms for s in active_sources)
                else:
                    min_interval_ms = 5_000
                await asyncio.sleep(max(min_interval_ms / 1000.0, 1.0))
            except asyncio.CancelledError:
                break
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("OPC UA connector loop error: {}", exc, exc_info=True)
                self._last_error = str(exc)
                await asyncio.sleep(5)

    async def _poll_source_once(self, source: OPCUASourceConfig) -> None:
        """Fetch one sample for every configured node of a source."""
        if Client is None:
            # No real OPC UA library available – emit fake heartbeat only.
            logger.debug("OPC UA client unavailable; skipping real polling for {}", source.id)
            return

        try:
            async with Client(url=source.endpoint_url) as client:
                # Basic security handling – full Sign&Encrypt is delegated to
                # asyncua; we only configure based on the mode/policy flags.
                if ua is not None:
                    if source.security_mode.lower() != "anonymous":
                        if source.username and source.password:
                            client.set_user(source.username)
                            client.set_password(source.password)

                # Simple node sampling
                for node_cfg in source.nodes:
                    node = client.get_node(node_cfg.node_id)
                    value = await node.read_value()
                    data_value = await node.read_data_value()
                    quality = str(getattr(data_value, "StatusCode", "Good"))
                    ts = getattr(data_value, "SourceTimestamp", None)

                    sample = normalize_opcua_sample(
                        alias=node_cfg.alias,
                        value=value,
                        quality=quality,
                        unit=node_cfg.unit,
                        timestamp_source=source.timestamp_source,
                        server_timestamp=ts,
                    )
                    await self._route_sample(source, node_cfg, sample)

        except Exception as exc:
            logger.error("Error polling OPC UA source {}: {}", source.id, exc)
            self._last_error = str(exc)

    async def _route_sample(
        self,
        source: OPCUASourceConfig,
        node_cfg: Any,
        sample: Dict[str, Any],
    ) -> None:
        """
        Route a normalized OPC UA sample into the existing sensor/machine +
        sensor_data pipeline. This mirrors the logic used in the MQTT ingestor
        but starts from the fixed OPC UA payload shape.
        """
        alias = sample["alias"]
        value = sample["value"]

        async with AsyncSessionLocal() as session:
            # 1. Ensure machine exists (use tags to build a synthetic machine id)
            machine_key = source.tags.get("machine") or "opcua-machine"
            machine = await machine_service.get_machine(session, machine_key)
            if not machine:
                from app.schemas.machine import MachineCreate

                machine = await machine_service.create_machine(
                    session,
                    MachineCreate(
                        name=machine_key,
                        status="online",
                        location=source.tags.get("line", ""),
                        metadata={"source": "opcua", "source_id": source.id},
                    ),
                )
                await session.commit()

            # 2. Ensure sensor exists
            sensor = await sensor_service.get_sensor(session, alias)
            if not sensor:
                from app.schemas.sensor import SensorCreate

                sensor = await sensor_service.create_sensor(
                    session,
                    SensorCreate(
                        name=alias,
                        machine_id=machine.id,
                        unit=node_cfg.unit or "",
                        metadata={
                            "source": "opcua",
                            "opcua_node_id": node_cfg.node_id,
                            "category": node_cfg.category,
                        },
                    ),
                )
                await session.commit()

            # 3. Write sensor data using existing service
            from app.schemas.sensor_data import SensorDataIn

            data_in = SensorDataIn(
                sensor_id=sensor.id,
                machine_id=machine.id,
                timestamp=sample["timestamp"],
                value=float(value) if isinstance(value, (int, float)) else 0.0,
                status=sample.get("quality") or "Good",
                metadata={
                    "unit": sample.get("unit"),
                    "source": "opcua",
                    "alias": alias,
                },
            )
            await sensor_data_service.ingest_sensor_data(session, data_in)

            # 4. Reuse alarm / AI logic (optional best‑effort)
            try:
                await alarm_service.auto_alarm_from_sensor_value(
                    session=session,
                    sensor=sensor,
                    machine_id=machine.id,
                    value=data_in.value,
                    timestamp=data_in.timestamp,
                )
                await session.commit()
            except Exception as exc:
                logger.debug("OPC UA alarm evaluation failed: {}", exc)


opcua_connector = OPCUAConnector(get_settings())



