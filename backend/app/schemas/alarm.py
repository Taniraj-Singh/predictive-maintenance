from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import AliasChoices, BaseModel, Field

from app.schemas.base import ORMBase


class AlarmCreate(BaseModel):
    machine_id: UUID
    sensor_id: Optional[UUID] = None
    prediction_id: Optional[UUID] = None
    severity: str
    message: str
    triggered_at: datetime
    metadata: Optional[dict] = Field(
        default=None,
        validation_alias=AliasChoices("metadata", "metadata_json"),
        serialization_alias="metadata",
    )


class AlarmUpdate(BaseModel):
    status: Optional[str] = None
    resolved_at: Optional[datetime] = None
    metadata: Optional[dict] = Field(
        default=None,
        validation_alias=AliasChoices("metadata", "metadata_json"),
        serialization_alias="metadata",
    )


class AlarmRead(ORMBase, AlarmCreate):
    status: str

