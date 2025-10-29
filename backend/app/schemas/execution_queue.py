from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from app.models.execution_queue import ExecutionQueueKind
from app.schemas.common import IdentifierModel, ORMModel


class ExecutionQueueBase(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    kind: ExecutionQueueKind = ExecutionQueueKind.CASE
    environment_id: UUID | None = None
    concurrency_limit: int | None = Field(default=None, ge=1)
    rate_limit_qps: float | None = Field(default=None, gt=0)
    enabled: bool = True
    is_default: bool | None = None
    labels: dict[str, list[str]] = Field(default_factory=dict)


class ExecutionQueueCreate(ExecutionQueueBase):
    pass


class ExecutionQueueUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    environment_id: UUID | None = None
    concurrency_limit: int | None = Field(default=None, ge=1)
    rate_limit_qps: float | None = Field(default=None, gt=0)
    enabled: bool | None = None
    is_default: bool | None = None
    labels: dict[str, list[str]] | None = None


class ExecutionQueueRead(IdentifierModel):
    project_id: UUID
    environment_id: UUID | None
    name: str
    routing_key: str
    kind: ExecutionQueueKind
    concurrency_limit: int | None
    rate_limit_qps: float | None
    enabled: bool
    is_default: bool
    labels: dict[str, list[str]]
