from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.common import IdentifierModel, ORMModel
from app.schemas.issue import IssueTemplatePayload


class AutoTicketRuleBase(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    integration_id: UUID
    filters: dict[str, Any] = Field(default_factory=dict)
    template: IssueTemplatePayload = Field(default_factory=IssueTemplatePayload)
    dedupe_window_minutes: int = Field(ge=1, le=1440, default=60)
    reopen_if_recurs: bool = True
    close_after_success_runs: int = Field(ge=0, le=1000, default=0)
    enabled: bool = True


class AutoTicketRuleCreate(AutoTicketRuleBase):
    pass


class AutoTicketRuleUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    integration_id: UUID | None = None
    filters: dict[str, Any] | None = None
    template: IssueTemplatePayload | None = None
    dedupe_window_minutes: int | None = Field(default=None, ge=1, le=1440)
    reopen_if_recurs: bool | None = None
    close_after_success_runs: int | None = Field(default=None, ge=0, le=1000)
    enabled: bool | None = None


class AutoTicketRuleRead(IdentifierModel):
    project_id: UUID
    integration_id: UUID
    name: str
    filters: dict[str, Any]
    template: IssueTemplatePayload
    dedupe_window_minutes: int
    reopen_if_recurs: bool
    close_after_success_runs: int
    enabled: bool
    created_by: UUID | None


__all__ = [
    "AutoTicketRuleBase",
    "AutoTicketRuleCreate",
    "AutoTicketRuleUpdate",
    "AutoTicketRuleRead",
]
