from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_current_user, require_viewer
from app.models.user import User
from app.schemas.sensor_data import SensorDataIn, SensorDataOut
from app.services import alarm_service, sensor_data_service, sensor_service
from app.models.sensor_data import SensorData

router = APIRouter(prefix="/sensor-data", tags=["sensor_data"])


@router.post("", response_model=SensorDataOut, status_code=status.HTTP_201_CREATED)
async def ingest_sensor_data(payload: SensorDataIn, session: AsyncSession = Depends(get_session)):
    sensor_data = await sensor_data_service.ingest_sensor_data(session, payload)
    sensor = await sensor_service.get_sensor(session, payload.sensor_id)
    if sensor:
        await alarm_service.auto_alarm_from_sensor_value(
            session=session,
            sensor=sensor,
            machine_id=payload.machine_id,
            value=payload.value,
            timestamp=payload.timestamp,
        )
    return sensor_data


@router.get("/logs", response_model=List[SensorDataOut])
async def get_sensor_data_logs(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_viewer),
    sensor_id: Optional[UUID] = Query(None),
    machine_id: Optional[UUID] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Get sensor data logs with filtering"""
    query = select(SensorData)
    
    conditions = []
    if sensor_id:
        conditions.append(SensorData.sensor_id == sensor_id)
    if machine_id:
        conditions.append(SensorData.machine_id == machine_id)
    if start_date:
        conditions.append(SensorData.timestamp >= start_date)
    if end_date:
        conditions.append(SensorData.timestamp <= end_date)
    
    if conditions:
        query = query.where(and_(*conditions))
    
    query = query.order_by(SensorData.timestamp.desc()).limit(limit).offset(offset)
    result = await session.execute(query)
    return list(result.scalars().all())

