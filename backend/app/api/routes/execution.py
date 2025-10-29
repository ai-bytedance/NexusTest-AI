from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import ProjectContext, require_project_member
from app.core.errors import ErrorCode, http_exception
from app.db.session import get_db
from app.models import ReportEntityType, ReportStatus, TestCase, TestReport, TestSuite
from app.schemas.test_report import ExecutionTriggerResponse
from app.services.reports.progress import publish_progress_event
from app.tasks.execute_case import execute_test_case
from app.tasks.execute_suite import execute_test_suite

router = APIRouter(prefix="/projects/{project_id}/execute", tags=["execution"])


def _get_test_case(db: Session, project_id: UUID, case_id: UUID) -> TestCase:
    stmt = (
        select(TestCase)
        .where(
            TestCase.id == case_id,
            TestCase.project_id == project_id,
            TestCase.is_deleted.is_(False),
        )
        .limit(1)
    )
    test_case = db.execute(stmt).scalar_one_or_none()
    if test_case is None:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Test case not found")
    return test_case


def _get_test_suite(db: Session, project_id: UUID, suite_id: UUID) -> TestSuite:
    stmt = (
        select(TestSuite)
        .where(
            TestSuite.id == suite_id,
            TestSuite.project_id == project_id,
            TestSuite.is_deleted.is_(False),
        )
        .limit(1)
    )
    test_suite = db.execute(stmt).scalar_one_or_none()
    if test_suite is None:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Test suite not found")
    return test_suite


def _create_report(
    db: Session,
    project_id: UUID,
    entity_type: ReportEntityType,
    entity_id: UUID,
) -> TestReport:
    report = TestReport(
        project_id=project_id,
        entity_type=entity_type,
        entity_id=entity_id,
        status=ReportStatus.PENDING,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.post("/case/{case_id}", response_model=ResponseEnvelope, status_code=status.HTTP_202_ACCEPTED)
def trigger_case_execution(
    case_id: UUID,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    test_case = _get_test_case(db, context.project.id, case_id)
    report = _create_report(db, context.project.id, ReportEntityType.CASE, test_case.id)

    async_result = execute_test_case.apply_async(
        kwargs={
            "report_id": str(report.id),
            "case_id": str(test_case.id),
            "project_id": str(context.project.id),
        },
        queue="cases",
    )

    report.metrics = {**(report.metrics or {}), "task_id": async_result.id}
    db.add(report)
    db.commit()
    db.refresh(report)

    publish_progress_event(
        str(report.id),
        "task_queued",
        payload={
            "task_id": async_result.id,
            "entity_type": report.entity_type.value,
            "entity_id": str(report.entity_id),
            "project_id": str(report.project_id),
        },
    )

    payload = ExecutionTriggerResponse(task_id=async_result.id, report_id=report.id)
    return success_response(payload.model_dump())


@router.post("/suite/{suite_id}", response_model=ResponseEnvelope, status_code=status.HTTP_202_ACCEPTED)
def trigger_suite_execution(
    suite_id: UUID,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    test_suite = _get_test_suite(db, context.project.id, suite_id)
    report = _create_report(db, context.project.id, ReportEntityType.SUITE, test_suite.id)

    async_result = execute_test_suite.apply_async(
        kwargs={
            "report_id": str(report.id),
            "suite_id": str(test_suite.id),
            "project_id": str(context.project.id),
        },
        queue="suites",
    )

    report.metrics = {**(report.metrics or {}), "task_id": async_result.id}
    db.add(report)
    db.commit()
    db.refresh(report)

    publish_progress_event(
        str(report.id),
        "task_queued",
        payload={
            "task_id": async_result.id,
            "entity_type": report.entity_type.value,
            "entity_id": str(report.entity_id),
            "project_id": str(report.project_id),
        },
    )

    payload = ExecutionTriggerResponse(task_id=async_result.id, report_id=report.id)
    return success_response(payload.model_dump())
