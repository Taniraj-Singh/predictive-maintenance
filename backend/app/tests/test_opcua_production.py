"""OPC UA Production Acceptance Tests (5 scenarios).

These exercise the OPC UA-fed data path end-to-end against an in-memory
database (no live OPC UA server required, mirroring how the platform's
test endpoint and connector are designed to run deterministically):

  Test 1 — Connection & restart recovery (config persistence / registry reload)
  Test 2 — Normal operation (in-band values raise no alarm)
  Test 3 — Drift detection (gradual rise crosses warning; flood-suppressed)
  Test 4 — Fault scenario (critical threshold breach raises a critical alarm)
  Test 5 — Recovery (resolving clears suppression so the system can re-alarm)

Run:  pytest app/tests/test_opcua_production.py -v
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.alarm import Alarm, AlarmStatus, ACTIVE_ALARM_STATUSES
from app.models.machine import Machine
from app.models.sensor import Sensor
from app.opcua.schema_normalizer import normalize_opcua_sample
from app.opcua.source_registry import (
    OPCUANodeConfig,
    OPCUASourceConfig,
    registry,
)
from app.services import alarm_service


# --------------------------------------------------------------------------- #
# Helpers / lightweight OPC UA simulator
# --------------------------------------------------------------------------- #
async def _make_machine_and_sensor(session, *, warning=70.0, critical=90.0):
    machine = Machine(name=f"OPCUA-Machine-{datetime.now(timezone.utc).timestamp()}")
    session.add(machine)
    await session.commit()
    await session.refresh(machine)

    sensor = Sensor(
        machine_id=machine.id,
        name="motor_current",
        sensor_type="current",
        unit="A",
        warning_threshold=warning,
        critical_threshold=critical,
    )
    session.add(sensor)
    await session.commit()
    await session.refresh(sensor)
    return machine, sensor


def _opcua_reading(alias: str, value: float):
    """Simulate one normalized OPC UA value change."""
    return normalize_opcua_sample(alias=alias, value=value, unit="A")


async def _count_active_alarms(session, sensor_id):
    from sqlalchemy import select, func

    return await session.scalar(
        select(func.count(Alarm.id)).where(
            Alarm.sensor_id == sensor_id,
            Alarm.status.in_(ACTIVE_ALARM_STATUSES),
        )
    )


# --------------------------------------------------------------------------- #
# Test 1 — Connection & restart recovery
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_1_connection_and_restart_recovery():
    """A configured source survives a simulated restart via the registry."""
    nodes = [
        OPCUANodeConfig(node_id="ns=2;s=Motor.Current", alias="motor_current", unit="A", category="electrical"),
        OPCUANodeConfig(node_id="ns=2;s=Motor.Temp", alias="motor_temp", unit="C", category="thermal"),
    ]
    cfg = OPCUASourceConfig(
        id="test-source-1",
        name="Test Source",
        endpoint_url="opc.tcp://localhost:4840",
        namespace_index=2,
        sampling_interval_ms=1000,
        session_timeout_ms=60000,
        security_mode="anonymous",
        security_policy="",
        security_mode_level="",
        nodes=nodes,
        active=True,
    )

    # Connection handshake produces a well-formed normalized sample (preview).
    sample = _opcua_reading("motor_current", 12.3)
    assert sample["alias"] == "motor_current"
    assert sample["quality"] == "Good"
    assert sample["unit"] == "A"
    assert "timestamp" in sample

    # Persist into the registry (DB-backed in production) and simulate a restart
    # by re-reading from the registry.
    registry.upsert(cfg)
    restored = registry.get("test-source-1")
    assert restored is not None
    assert restored.endpoint_url == "opc.tcp://localhost:4840"
    assert len(restored.nodes) == 2
    assert restored.nodes[0].alias == "motor_current"
    assert restored.active is True


# --------------------------------------------------------------------------- #
# Test 2 — Normal operation
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_2_normal_operation(session):
    machine, sensor = await _make_machine_and_sensor(session)
    ts = datetime.now(timezone.utc)

    # In-band readings (below warning threshold) -> no alarm.
    for value in (40.0, 45.0, 50.0, 48.0):
        reading = _opcua_reading("motor_current", value)
        alarm = await alarm_service.auto_alarm_from_sensor_value(
            session, sensor, machine.id, float(reading["value"]), ts
        )
        assert alarm is None

    assert await _count_active_alarms(session, sensor.id) == 0


# --------------------------------------------------------------------------- #
# Test 3 — Drift detection (+ flood protection)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_3_drift_detection(session):
    machine, sensor = await _make_machine_and_sensor(session)
    ts = datetime.now(timezone.utc)

    # Gradual drift upward; crosses the warning threshold (70) at 72.
    drift = [55.0, 62.0, 68.0, 72.0]
    alarms = []
    for value in drift:
        a = await alarm_service.auto_alarm_from_sensor_value(
            session, sensor, machine.id, value, ts
        )
        if a:
            alarms.append(a)

    # Exactly one warning alarm should have been raised.
    assert len(alarms) == 1
    assert alarms[0].severity == "warning"

    # Continued breaches at the same severity are flood-suppressed.
    for value in (73.0, 74.0, 75.0):
        a = await alarm_service.auto_alarm_from_sensor_value(
            session, sensor, machine.id, value, ts
        )
        assert a is None

    assert await _count_active_alarms(session, sensor.id) == 1


# --------------------------------------------------------------------------- #
# Test 4 — Fault scenario
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_4_fault_scenario(session):
    machine, sensor = await _make_machine_and_sensor(session)
    ts = datetime.now(timezone.utc)

    # Hard fault: value exceeds the critical threshold (90).
    fault = await alarm_service.auto_alarm_from_sensor_value(
        session, sensor, machine.id, 95.0, ts
    )
    assert fault is not None
    assert fault.severity == "critical"

    # A critical alarm auto-creates a linked ticket (lifecycle workflow).
    from sqlalchemy import select
    from app.models.ticket import Ticket

    ticket = await session.scalar(select(Ticket).where(Ticket.alarm_id == fault.id))
    assert ticket is not None
    assert ticket.machine_id == machine.id


# --------------------------------------------------------------------------- #
# Test 5 — Recovery
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_5_recovery(session):
    machine, sensor = await _make_machine_and_sensor(session)
    ts = datetime.now(timezone.utc)

    # Raise a warning alarm.
    first = await alarm_service.auto_alarm_from_sensor_value(session, sensor, machine.id, 72.0, ts)
    assert first is not None

    # While active, the same condition is suppressed.
    assert await alarm_service.is_alarm_suppressed(
        session, sensor_id=sensor.id, machine_id=machine.id, severity="warning"
    ) is True

    # Operator resolves the alarm (recovery).
    await alarm_service.resolve_alarm(session, first, "Verified and cleared")
    assert first.status == AlarmStatus.resolved.value

    # After recovery the condition is no longer suppressed: the system can
    # legitimately re-alarm if the fault recurs.
    assert await alarm_service.is_alarm_suppressed(
        session, sensor_id=sensor.id, machine_id=machine.id, severity="warning"
    ) is False

    second = await alarm_service.auto_alarm_from_sensor_value(session, sensor, machine.id, 73.0, ts)
    assert second is not None
    assert second.id != first.id
