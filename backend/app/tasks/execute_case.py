from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.celery import celery_app
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.logging import get_logger
from app.models import ReportEntityType, ReportStatus, TestCase, TestReport
from app.services.assertions.engine import AssertionEngine
from app.services.execution.context import ExecutionContext
from app.services.runner.http_runner import HttpRunner, HttpRunnerError

logger = get_logger()

NETWORK_RETRY_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 2
MAX_BACKOFF_DELAY_SECONDS = 30
assertion_engine = AssertionEngine()


def get_http_runner() -> HttpRunner:
    settings = get_settings()
    return HttpRunner(settings.request_timeout_seconds, settings.max_response_size_bytes)


@celery_app.task(name="app.tasks.execute_case.execute_test_case", bind=True, queue="cases")
def execute_test_case(self, report_id: str, case_id: str, project_id: str) -> None:
    runner = get_http_runner()
    session = SessionLocal()
    report_uuid = uuid.UUID(report_id)
    case_uuid = uuid.UUID(case_id)
    project_uuid = uuid.UUID(project_id)

    try:
        report = _get_report(session, report_uuid, project_uuid, ReportEntityType.CASE, case_uuid)
        case = _get_case(session, case_uuid, project_uuid)

        _mark_report_running(session, report, self.request.id)

        context = ExecutionContext()
        attempts = 0
        last_error: HttpRunnerError | None = None
        while attempts < NETWORK_RETRY_ATTEMPTS:
            attempts += 1
            try:
                result = runner.execute(case.inputs, context)
                break
            except HttpRunnerError as exc:
                last_error = exc
                if attempts >= NETWORK_RETRY_ATTEMPTS:
                    _mark_runner_error(session, report, exc, self.request.id)
                    return
                delay = min(BACKOFF_BASE_SECONDS ** attempts, MAX_BACKOFF_DELAY_SECONDS)
                logger.warning("case_runner_retry", attempt=attempts, delay_seconds=delay, error=str(exc))
                time.sleep(delay)
        else:
            if last_error is not None:
                _mark_runner_error(session, report, last_error, self.request.id)
                return
            raise RuntimeError("HTTP runner failed without exception")

        passed, assertion_results = assertion_engine.evaluate(case.assertions, result.context_data, context)
        finished_at = datetime.now(timezone.utc)
        metrics = _merge_dicts(result.metrics, {"task_id": self.request.id})

        report.status = ReportStatus.PASSED if passed else ReportStatus.FAILED
        report.finished_at = finished_at
        report.duration_ms = result.metrics.get("duration_ms")
        report.request_payload = result.request_payload
        report.response_payload = result.response_payload
        report.assertions_result = {
            "passed": passed,
            "results": [item.to_dict() for item in assertion_results],
        }
        report.metrics = metrics
        session.add(report)
        session.commit()

    except Exception as exc:  # pragma: no cover - unexpected safeguard
        session.rollback()
        logger.error("execute_case_error", report_id=report_id, error=str(exc))
        report = session.get(TestReport, report_uuid)
        if report:
            _mark_unexpected_error(session, report, str(exc), self.request.id)
        raise
    finally:
        session.close()


def _get_report(
    session: Session,
    report_id: uuid.UUID,
    project_id: uuid.UUID,
    entity_type: ReportEntityType,
    entity_id: uuid.UUID,
) -> TestReport:
    stmt = (
        select(TestReport)
        .where(
            TestReport.id == report_id,
            TestReport.project_id == project_id,
            TestReport.entity_type == entity_type,
            TestReport.entity_id == entity_id,
            TestReport.is_deleted.is_(False),
        )
        .limit(1)
    )
    report = session.execute(stmt).scalar_one_or_none()
    if report is None:
        raise ValueError("Test report not found for execution task")
    return report


def _get_case(session: Session, case_id: uuid.UUID, project_id: uuid.UUID) -> TestCase:
    stmt = (
        select(TestCase)
        .where(
            TestCase.id == case_id,
            TestCase.project_id == project_id,
            TestCase.is_deleted.is_(False),
        )
        .limit(1)
    )
    case = session.execute(stmt).scalar_one_or_none()
    if case is None:
        raise ValueError("Test case not found for execution task")
    return case


def _mark_report_running(session: Session, report: TestReport, task_id: str) -> None:
    report.status = ReportStatus.RUNNING
    report.started_at = datetime.now(timezone.utc)
    report.metrics = _merge_dicts(report.metrics, {"task_id": task_id})
    session.add(report)
    session.commit()


def _mark_runner_error(session: Session, report: TestReport, error: HttpRunnerError, task_id: str) -> None:
    finished_at = datetime.now(timezone.utc)
    report.status = ReportStatus.ERROR
    report.finished_at = finished_at
    report.duration_ms = error.metrics.get("duration_ms")
    report.request_payload = error.request_payload
    response_payload = error.response_payload or {"error": str(error)}
    report.response_payload = response_payload
    report.assertions_result = {
        "passed": False,
        "results": [],
        "error": str(error),
    }
    metrics = _merge_dicts(error.metrics, {"task_id": task_id})
    if "status" not in metrics:
        metrics["status"] = "error"
    report.metrics = metrics
    session.add(report)
    session.commit()


def _mark_unexpected_error(session: Session, report: TestReport, message: str, task_id: str) -> None:
    finished_at = datetime.now(timezone.utc)
    report.status = ReportStatus.ERROR
    report.finished_at = finished_at
    report.assertions_result = {
        "passed": False,
        "results": [],
        "error": message,
    }
    report.metrics = _merge_dicts(report.metrics, {"task_id": task_id, "status": "error"})
    session.add(report)
    session.commit()


def _merge_dicts(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    payload = dict(base or {})
    payload.update(updates)
    return payload
