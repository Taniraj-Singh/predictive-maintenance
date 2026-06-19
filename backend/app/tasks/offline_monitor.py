"""Offline-sensor detection background task.

Periodically scans active sensors whose `last_seen` is older than the configured
threshold and raises a single (flood-protected) `info`/`warning` alarm so that
operators are notified when a sensor stops reporting. Re-arms automatically once
the sensor reports again (its `last_seen` advances).
"""
import asyncio
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.alarm import AlarmSeverity
from app.models.sensor import Sensor
from app.schemas.alarm import AlarmCreate
from app.services import alarm_service

settings = get_settings()


async def scan_offline_sensors() -> int:
    """Run one offline-sensor scan. Returns the number of offline alarms raised."""
    threshold = settings.sensor_offline_after_seconds
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=threshold)
    raised = 0

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Sensor).where(Sensor.is_active.is_(True))
        )
        sensors = result.scalars().all()

        for sensor in sensors:
            last_seen = sensor.last_seen
            # Never-seen sensors are skipped until they report at least once.
            if last_seen is None:
                continue
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            if last_seen > cutoff:
                continue  # still online

            severity = AlarmSeverity.warning.value
            if await alarm_service.is_alarm_suppressed(
                session,
                sensor_id=sensor.id,
                machine_id=sensor.machine_id,
                severity=severity,
            ):
                continue

            age = int((datetime.now(timezone.utc) - last_seen).total_seconds())
            payload = AlarmCreate(
                machine_id=sensor.machine_id,
                sensor_id=sensor.id,
                prediction_id=None,
                severity=severity,
                message=f"Sensor '{sensor.name}' offline: no data for {age}s",
                triggered_at=datetime.now(timezone.utc),
                metadata={"reason": "offline", "age_seconds": age, "threshold_seconds": threshold},
            )
            alarm = await alarm_service.create_alarm(session, payload)
            try:
                from app.services import ticket_service
                await ticket_service.ensure_ticket_for_alarm(session, alarm)
            except Exception as e:  # pragma: no cover - defensive
                logger.debug(f"ensure_ticket_for_alarm (offline) failed: {e}")
            raised += 1

    if raised:
        logger.warning("Offline-sensor scan raised {} alarm(s)", raised)
    return raised


async def start_offline_monitor() -> None:
    """Long-running loop; scans every `sensor_offline_scan_interval_seconds`."""
    interval = settings.sensor_offline_scan_interval_seconds
    logger.info("🛰️  Offline-sensor monitor started (interval={}s, threshold={}s)",
                interval, settings.sensor_offline_after_seconds)
    while True:
        try:
            await scan_offline_sensors()
        except Exception as e:  # pragma: no cover - keep loop alive
            logger.error(f"Offline-sensor scan failed: {e}")
        await asyncio.sleep(interval)
