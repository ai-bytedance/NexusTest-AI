from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.models.notifier import NotifierType
from app.models.notifier_event import NotifierEventStatus, NotifierEventType
from app.schemas.common import IdentifierModel, ORMModel


class NotifierBase(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    type: NotifierType
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class NotifierCreate(NotifierBase):
    pass


class NotifierUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    type: NotifierType | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class NotifierRead(IdentifierModel):
    project_id: UUID
    name: str
    type: NotifierType
    config: dict[str, Any]
    enabled: bool
    created_by: UUID


class NotifierTestRequest(ORMModel):
    message: str | None = Field(default=None, max_length=1024)


class NotifierEventRead(IdentifierModel):
    project_id: UUID
    notifier_id: UUID
    event: NotifierEventType
    payload: dict[str, Any]
    status: NotifierEventStatus
    error_message: str | None
    retry_count: int
    created_at: datetime
    updated_at: datetime
    last_attempted_at: datetime | None
    processed_at: datetime | None


__all__ = [
    "NotifierCreate",
    "NotifierUpdate",
    "NotifierRead",
    "NotifierTestRequest",
    "NotifierEventRead",
]
