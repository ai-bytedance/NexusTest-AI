from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import get_current_user
from app.core.errors import ErrorCode, http_exception
from app.db.session import get_db
from app.models import ProjectMember, TestReport, User
from app.schemas.test_report import TaskStatusRead, TestReportRead
from app.tasks import celery_app

router = APIRouter(tags=["reports"])


@router.get("/reports/{report_id}", response_model=ResponseEnvelope)
def get_report(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    report = db.get(TestReport, report_id)
    if report is None or report.is_deleted:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Report not found")
    _ensure_membership(db, report.project_id, current_user.id)
    payload = TestReportRead.model_validate(report)
    return success_response(payload.model_dump())


@router.get("/tasks/{task_id}", response_model=ResponseEnvelope, tags=["tasks"])
def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    async_result = celery_app.AsyncResult(task_id)
    report = _find_report_by_task_id(db, task_id)
    report_id: UUID | None = None
    if report is not None:
        _ensure_membership(db, report.project_id, current_user.id)
        report_id = report.id
    status_value = async_result.status.lower() if async_result.status else "pending"
    payload = TaskStatusRead(task_id=task_id, status=status_value, report_id=report_id)
    return success_response(payload.model_dump())


def _ensure_membership(db: Session, project_id: UUID, user_id: UUID) -> None:
    stmt = (
        select(ProjectMember)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
            ProjectMember.is_deleted.is_(False),
        )
        .limit(1)
    )
    membership = db.execute(stmt).scalar_one_or_none()
    if membership is None:
        raise http_exception(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.NO_PERMISSION,
            "You do not have access to this project",
        )


def _find_report_by_task_id(db: Session, task_id: str) -> TestReport | None:
    stmt = select(TestReport).where(TestReport.is_deleted.is_(False))
    reports = db.execute(stmt).scalars().all()
    for report in reports:
        metrics = report.metrics or {}
        if str(metrics.get("task_id")) == task_id:
            return report
    return None
