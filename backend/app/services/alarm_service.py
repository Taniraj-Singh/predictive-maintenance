from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from loguru import logger
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.alarm import Alarm, AlarmSeverity, AlarmStatus, ACTIVE_ALARM_STATUSES
from app.models.sensor import Sensor
from app.schemas.alarm import AlarmCreate
from app.services import notification_service, ticket_service

settings = get_settings()


async def is_alarm_suppressed(
    session: AsyncSession,
    *,
    sensor_id: Optional[UUID],
    machine_id: UUID,
    severity: str,
    window_seconds: Optional[int] = None,
) -> bool:
    """Flood protection.

    Returns True when an equivalent *active* (open/acknowledged) alarm already
    exists for the same sensor (or machine when there is no sensor) at the same
    severity within the configured window. This implements state-change based
    deduplication: a stable industrial signal that keeps crossing a threshold
    produces a single alarm until it is resolved, instead of an alarm storm.
    """
    if window_seconds is None:
        window_seconds = settings.alarm_flood_window_seconds
    since = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)

    stmt = select(Alarm.id).where(
        Alarm.severity == severity,
        Alarm.status.in_(ACTIVE_ALARM_STATUSES),
        Alarm.triggered_at >= since,
    )
    if sensor_id is not None:
        stmt = stmt.where(Alarm.sensor_id == sensor_id)
    else:
        stmt = stmt.where(Alarm.machine_id == machine_id, Alarm.sensor_id.is_(None))

    existing = await session.scalar(stmt.order_by(desc(Alarm.triggered_at)).limit(1))
    return existing is not None


def _prepare_payload(data: dict) -> dict:
    metadata = data.pop("metadata", None)
    if metadata is not None:
        data["metadata_json"] = metadata
    return data


def _determine_severity(sensor: Sensor, value: float) -> Optional[str]:
    if sensor.critical_threshold is not None and value >= float(sensor.critical_threshold):
        return AlarmSeverity.critical.value
    if sensor.warning_threshold is not None and value >= float(sensor.warning_threshold):
        return AlarmSeverity.warning.value
    if sensor.min_threshold is not None and value <= float(sensor.min_threshold):
        return AlarmSeverity.warning.value
    return None


async def create_alarm(
    session: AsyncSession,
    payload: AlarmCreate,
) -> Alarm:
    data = _prepare_payload(payload.model_dump())
    alarm = Alarm(**data, status=AlarmStatus.open.value)
    session.add(alarm)
    await session.commit()
    await session.refresh(alarm)
    
    # Broadcast real-time update
    try:
        from app.api.routers.realtime import broadcast_update
        await broadcast_update(
            "alarm.created",
            {
                "id": str(alarm.id),
                "machine_id": str(alarm.machine_id),
                "sensor_id": str(alarm.sensor_id) if alarm.sensor_id else None,
                "severity": alarm.severity,
                "message": alarm.message,
                "status": alarm.status,
                "triggered_at": alarm.triggered_at.isoformat() if alarm.triggered_at else None,
            }
        )
    except Exception as e:
        logger.debug(f"Failed to broadcast alarm update: {e}")
    
    return alarm


async def resolve_alarm(session: AsyncSession, alarm: Alarm, resolution_notes: Optional[str] = None) -> Alarm:
    alarm.status = AlarmStatus.resolved.value
    alarm.resolved_at = datetime.now(timezone.utc)
    if resolution_notes:
        if alarm.metadata_json is None:
            alarm.metadata_json = {}
        alarm.metadata_json["resolution_notes"] = resolution_notes
    await session.commit()
    await session.refresh(alarm)
    
    # Broadcast real-time update
    try:
        from app.api.routers.realtime import broadcast_update
        await broadcast_update(
            "alarm.updated",
            {
                "id": str(alarm.id),
                "machine_id": str(alarm.machine_id),
                "status": alarm.status,
                "resolved_at": alarm.resolved_at.isoformat() if alarm.resolved_at else None,
            }
        )
    except Exception as e:
        logger.debug(f"Failed to broadcast alarm update: {e}")
    
    return alarm


async def auto_alarm_from_sensor_value(
    session: AsyncSession,
    sensor: Sensor,
    machine_id: UUID,
    value: float,
    timestamp: datetime,
) -> Optional[Alarm]:
    severity = _determine_severity(sensor, value)
    if not severity:
        return None

    # Flood protection: skip if an equivalent active alarm already exists.
    if await is_alarm_suppressed(
        session, sensor_id=sensor.id, machine_id=machine_id, severity=severity
    ):
        logger.debug("Alarm suppressed (flood protection) for sensor {}", sensor.id)
        return None

    payload = AlarmCreate(
        machine_id=machine_id,
        sensor_id=sensor.id,
        prediction_id=None,
        severity=severity,
        message=f"{sensor.name} reported {value} {sensor.unit or ''}",
        triggered_at=timestamp,
        metadata={"value": value},
    )
    alarm = await create_alarm(session, payload)
    notification_service.enqueue_alarm_notification(alarm, sensor)
    await ticket_service.ensure_ticket_for_alarm(session, alarm)
    logger.warning("Alarm created for sensor {} value {}", sensor.id, value)
    # Note: broadcast_update is already called in create_alarm
    return alarm

