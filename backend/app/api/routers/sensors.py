from typing import List, Optional
from uuid import UUID
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_current_user, require_engineer, require_admin
from app.models.user import User
from app.schemas.sensor import SensorCreate, SensorRead, SensorUpdate
from app.services import sensor_service
from app.models.sensor_data import SensorData

router = APIRouter(prefix="/sensors", tags=["sensors"])


def _to_read(sensor) -> SensorRead:
    """Build a SensorRead from an ORM Sensor, avoiding the SQLAlchemy `metadata` clash."""
    return SensorRead(
        id=sensor.id,
        machine_id=sensor.machine_id,
        name=sensor.name,
        sensor_type=sensor.sensor_type,
        unit=sensor.unit,
        min_threshold=float(sensor.min_threshold) if sensor.min_threshold is not None else None,
        max_threshold=float(sensor.max_threshold) if sensor.max_threshold is not None else None,
        warning_threshold=float(sensor.warning_threshold) if sensor.warning_threshold is not None else None,
        critical_threshold=float(sensor.critical_threshold) if sensor.critical_threshold is not None else None,
        metadata=sensor.metadata_json,
        is_active=getattr(sensor, "is_active", True),
        last_seen=getattr(sensor, "last_seen", None),
        created_at=sensor.created_at,
        updated_at=sensor.updated_at,
    )


@router.get("", response_model=List[SensorRead])
async def list_sensors(
    machine_id: Optional[UUID] = Query(default=None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    sensors = await sensor_service.list_sensors(session, machine_id)
    return [_to_read(s) for s in sensors]


@router.post("", response_model=SensorRead, status_code=status.HTTP_201_CREATED)
async def create_sensor(
    payload: SensorCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_engineer),
):
    sensor = await sensor_service.create_sensor(session, payload)
    return _to_read(sensor)


@router.get("/{sensor_id}", response_model=SensorRead)
async def get_sensor(
    sensor_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    sensor = await sensor_service.get_sensor(session, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return _to_read(sensor)


@router.patch("/{sensor_id}", response_model=SensorRead)
async def update_sensor(
    sensor_id: UUID,
    payload: SensorUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_engineer),
):
    sensor = await sensor_service.get_sensor(session, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    sensor = await sensor_service.update_sensor(session, sensor, payload)
    return _to_read(sensor)


@router.delete("/{sensor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sensor(
    sensor_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_admin),
):
    sensor = await sensor_service.get_sensor(session, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    await sensor_service.delete_sensor(session, sensor)


@router.post("/{sensor_id}/activate", response_model=SensorRead)
async def activate_sensor(
    sensor_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_engineer),
):
    sensor = await sensor_service.get_sensor(session, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    sensor = await sensor_service.set_sensor_active(session, sensor, True)
    return _to_read(sensor)


@router.post("/{sensor_id}/deactivate", response_model=SensorRead)
async def deactivate_sensor(
    sensor_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_engineer),
):
    sensor = await sensor_service.get_sensor(session, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    sensor = await sensor_service.set_sensor_active(session, sensor, False)
    return _to_read(sensor)


@router.get("/{sensor_id}/health")
async def get_sensor_health(
    sensor_id: UUID,
    offline_after_seconds: int = Query(120, ge=10, le=86400),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Report a sensor's health: active flag, last_seen, and online/offline state."""
    sensor = await sensor_service.get_sensor(session, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    last_seen = getattr(sensor, "last_seen", None)
    online = False
    age_seconds = None
    if last_seen is not None:
        now = datetime.now(last_seen.tzinfo) if last_seen.tzinfo else datetime.utcnow()
        age_seconds = (now - last_seen).total_seconds()
        online = age_seconds <= offline_after_seconds
    return {
        "sensor_id": str(sensor_id),
        "is_active": getattr(sensor, "is_active", True),
        "last_seen": last_seen.isoformat() if last_seen else None,
        "age_seconds": age_seconds,
        "online": online,
        "state": "online" if online else "offline",
    }


@router.get("/{sensor_id}/trend")
async def get_sensor_trend(
    sensor_id: UUID,
    interval: str = Query("24h", regex="^(1h|6h|24h|7d|30d)$"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get sensor trend data for the specified interval"""
    sensor = await sensor_service.get_sensor(session, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    
    # Parse interval
    interval_map = {
        "1h": timedelta(hours=1),
        "6h": timedelta(hours=6),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }
    delta = interval_map.get(interval, timedelta(hours=24))
    since = datetime.utcnow() - delta
    
    # Get sensor data points
    data_points = await session.scalars(
        select(SensorData)
        .where(and_(SensorData.sensor_id == sensor_id, SensorData.timestamp >= since))
        .order_by(SensorData.timestamp.asc())
    )
    
    points = [
        {
            "timestamp": point.timestamp.isoformat(),
            "value": float(point.value),
            "status": point.status,
        }
        for point in data_points
    ]
    
    # Calculate statistics
    if points:
        values = [p["value"] for p in points]
        return {
            "sensor_id": str(sensor_id),
            "interval": interval,
            "points": points,
            "statistics": {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
            },
        }
    else:
        return {
            "sensor_id": str(sensor_id),
            "interval": interval,
            "points": [],
            "statistics": None,
        }

