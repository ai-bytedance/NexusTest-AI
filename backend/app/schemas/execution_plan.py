from __future__ import annotations

from datetime import datetime
from typing import List
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.models.execution_plan import ExecutionPlanType
from app.schemas.common import IdentifierModel, ORMModel


class ExecutionPlanBase(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    type: ExecutionPlanType
    cron_expr: str | None = Field(default=None, max_length=255)
    interval_seconds: int | None = Field(default=None, ge=1)
    enabled: bool = True
    timezone: str = Field(default="UTC", max_length=64)
    suite_ids: List[UUID] = Field(default_factory=list, min_length=1)

    @field_validator("suite_ids", mode="before")
    @classmethod
    def validate_suite_ids(cls, value: List[UUID] | List[str]) -> List[UUID]:
        if not value:
            raise ValueError("At least one suite must be associated with the plan")
        return [UUID(str(item)) for item in value]

    @model_validator(mode="after")
    def validate_schedule_fields(self) -> "ExecutionPlanBase":
        if self.type == ExecutionPlanType.CRON:
            if not self.cron_expr:
                raise ValueError("cron_expr is required for cron-based plans")
            self.interval_seconds = None
        elif self.type == ExecutionPlanType.INTERVAL:
            if self.interval_seconds is None or self.interval_seconds <= 0:
                raise ValueError("interval_seconds must be greater than zero for interval plans")
            self.cron_expr = None
        return self


class ExecutionPlanCreate(ExecutionPlanBase):
    pass


class ExecutionPlanUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    type: ExecutionPlanType | None = None
    cron_expr: str | None = Field(default=None, max_length=255)
    interval_seconds: int | None = Field(default=None, ge=1)
    enabled: bool | None = None
    timezone: str | None = Field(default=None, max_length=64)
    suite_ids: List[UUID] | None = None

    @field_validator("suite_ids", mode="before")
    @classmethod
    def validate_suite_ids(cls, value: List[UUID] | List[str] | None) -> List[UUID] | None:
        if value is None:
            return None
        if not value:
            raise ValueError("At least one suite must be associated with the plan")
        return [UUID(str(item)) for item in value]


class ExecutionPlanRead(IdentifierModel):
    project_id: UUID
    name: str
    type: ExecutionPlanType
    cron_expr: str | None
    interval_seconds: int | None
    enabled: bool
    timezone: str
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_by: UUID
    suite_ids: List[UUID]


class ExecutionPlanRunResponse(ORMModel):
    task_id: str
    plan_id: UUID


__all__ = [
    "ExecutionPlanCreate",
    "ExecutionPlanUpdate",
    "ExecutionPlanRead",
    "ExecutionPlanRunResponse",
]
