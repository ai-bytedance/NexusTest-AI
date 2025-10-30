from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.authz import require_system_admin
from app.db.session import get_db
from app.logging import get_logger
from app.models import BackupRun
from app.models.user import User
from app.schemas.backup import BackupRunSummary, BackupStatusResponse
from app.tasks.backups import run_backup as run_backup_task

logger = get_logger()

router = APIRouter(prefix="/admin/backups", tags=["admin-backups"])


def _to_summary(run: BackupRun) -> BackupRunSummary:
    metadata: dict[str, Any] | None
    if isinstance(run.metadata, dict):
        metadata = run.metadata
    else:
        metadata = None
    storages = [value for value in (run.storage_targets or "").split(",") if value]
    return BackupRunSummary(
        id=run.id,
        started_at=run.started_at,
        finished_at=run.finished_at,
        status=run.status.value,
        storage_targets=storages,
        location=run.location,
        size_bytes=run.size_bytes,
        checksum=run.checksum,
        triggered_by=run.triggered_by,
        retention_class=run.retention_class,
        duration_seconds=run.duration_seconds,
        verified_at=run.verified_at,
        verify_notes=run.verify_notes,
        metadata=metadata,
    )


@router.get("/status", response_model=BackupStatusResponse)
def get_backup_status(
    db: Session = Depends(get_db),
    _: Any = Depends(require_system_admin),
) -> BackupStatusResponse:
    runs = (
        db.execute(
            select(BackupRun)
            .where(BackupRun.is_deleted.is_(False))
            .order_by(BackupRun.started_at.desc())
            .limit(20)
        )
        .scalars()
        .all()
    )
    summaries = [_to_summary(item) for item in runs]
    latest = summaries[0] if summaries else None
    return BackupStatusResponse(latest=latest, recent=summaries)


@router.post("/run-now", status_code=status.HTTP_202_ACCEPTED)
def trigger_backup(
    current_user: User = Depends(require_system_admin),
) -> dict[str, str]:
    triggered_by = f"user:{current_user.id}"
    async_result = run_backup_task.delay(triggered_by=triggered_by)
    logger.info("backup_manual_trigger", user_id=str(current_user.id), task_id=async_result.id)
    return {"task_id": async_result.id}
