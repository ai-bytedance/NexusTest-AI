from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.execution_routing import AgentSelectionPolicy
from app.models.test_report import ReportEntityType, ReportStatus
from app.schemas.common import IdentifierModel, ORMModel


class TestReportRead(IdentifierModel):
    project_id: UUID
    entity_type: ReportEntityType
    entity_id: UUID
    status: ReportStatus
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    assertions_result: dict[str, Any]
    metrics: dict[str, Any]
    summary: str | None
    parent_report_id: UUID | None
    run_number: int
    retry_attempt: int
    policy_snapshot: dict[str, Any]
    queue_id: UUID | None
    agent_id: UUID | None
    agent_tags: list[str]
    agent_selection_policy: AgentSelectionPolicy | None


class ReportSummarizeRequest(BaseModel):
    overwrite: bool = False


class ExecutionTriggerResponse(ORMModel):
    task_id: str
    report_id: UUID
    queue_id: UUID | None = None
    agent_id: UUID | None = None


class TaskStatusRead(ORMModel):
    task_id: str
    status: str
    report_id: UUID | None = None
