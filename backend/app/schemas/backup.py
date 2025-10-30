from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class BackupRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    started_at: datetime
    finished_at: datetime | None
    status: str
    storage_targets: list[str]
    location: str
    size_bytes: int | None
    checksum: str | None
    triggered_by: str | None
    retention_class: str
    duration_seconds: float | None
    verified_at: datetime | None
    verify_notes: str | None
    metadata: dict[str, Any] | None


class BackupStatusResponse(BaseModel):
    latest: BackupRunSummary | None
    recent: list[BackupRunSummary]


__all__ = ["BackupRunSummary", "BackupStatusResponse"]
