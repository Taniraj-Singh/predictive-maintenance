from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import AliasChoices, BaseModel, Field

from app.schemas.base import ORMBase


class TicketCreate(BaseModel):
    machine_id: UUID
    alarm_id: Optional[UUID] = None
    title: str
    priority: str = "medium"
    assignee: Optional[str] = None
    description: Optional[str] = None
    due_at: Optional[datetime] = None
    auto_created: bool = True
    metadata: Optional[dict] = Field(
        default=None,
        validation_alias=AliasChoices("metadata", "metadata_json"),
        serialization_alias="metadata",
    )


class TicketUpdate(BaseModel):
    status: Optional[str] = None
    assignee: Optional[str] = None
    resolution_notes: Optional[str] = None
    due_at: Optional[datetime] = None
    metadata: Optional[dict] = Field(
        default=None,
        validation_alias=AliasChoices("metadata", "metadata_json"),
        serialization_alias="metadata",
    )


class TicketRead(ORMBase, TicketCreate):
    status: str

