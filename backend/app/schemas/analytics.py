from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.analytics_fail_cluster import AnalyticsFailClusterStatus
from app.schemas.common import IdentifierModel


class FailureClusterPoint(BaseModel):
    date: str
    count: int


class FailureClusterSummary(IdentifierModel):
    project_id: UUID
    signature_hash: str
    title: str
    pattern: str | None = None
    status: AnalyticsFailClusterStatus
    count: int
    first_seen_at: datetime
    last_seen_at: datetime
    sample_report_ids: list[UUID] = Field(default_factory=list)
    recent_count: int = 0
    sparkline: list[int] = Field(default_factory=list)


class FailureClusterDetail(FailureClusterSummary):
    sample_reports: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[FailureClusterPoint] = Field(default_factory=list)


class FailureClusterUpdateRequest(BaseModel):
    status: AnalyticsFailClusterStatus | None = None
    title: str | None = None
    pattern: str | None = None
    merge_source_ids: list[UUID] | None = None
    remove_report_ids: list[UUID] | None = None


class FlakyEntitySummary(BaseModel):
    entity_type: str
    entity_id: UUID
    latest_report_id: UUID
    flakiness_score: float
    is_flaky: bool
    name: str | None = None
    pass_count: int = 0
    fail_count: int = 0
    transitions: int = 0
    recent_reports: list[dict[str, Any]] = Field(default_factory=list)
