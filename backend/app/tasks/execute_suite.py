from __future__ import annotations

import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.celery import celery_app
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.logging import get_logger
from app.models import ReportEntityType, ReportStatus, TestCase, TestReport, TestSuite
from app.services.assertions.engine import AssertionEngine
from app.services.execution.context import ExecutionContext, render_value
from app.services.runner.http_runner import HttpRunner, HttpRunnerError

logger = get_logger()

NETWORK_RETRY_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 2
MAX_BACKOFF_DELAY_SECONDS = 30
assertion_engine = AssertionEngine()


def get_http_runner() -> HttpRunner:
    settings = get_settings()
    return HttpRunner(settings.request_timeout_seconds, settings.max_response_size_bytes)


@celery_app.task(name="app.tasks.execute_suite.execute_test_suite", bind=True, queue="suites")
def execute_test_suite(self, report_id: str, suite_id: str, project_id: str) -> None:
    runner = get_http_runner()
    session = SessionLocal()
    report_uuid = uuid.UUID(report_id)
    suite_uuid = uuid.UUID(suite_id)
    project_uuid = uuid.UUID(project_id)

    try:
        report = _get_report(session, report_uuid, project_uuid, ReportEntityType.SUITE, suite_uuid)
        suite = _get_suite(session, suite_uuid, project_uuid)

        _mark_report_running(session, report, self.request.id)

        context = ExecutionContext(variables=deepcopy(suite.variables) if isinstance(suite.variables, dict) else {})
        case_cache: dict[uuid.UUID, TestCase] = {}

        request_steps: list[dict[str, Any]] = []
        response_steps: list[dict[str, Any]] = []
        assertion_steps: list[dict[str, Any]] = []
        metric_steps: list[dict[str, Any]] = []
        total_duration = 0
        total_response_size = 0
        overall_passed = True
        overall_error: str | None = None

        steps = suite.steps if isinstance(suite.steps, list) else []
        for index, raw_step in enumerate(steps):
            if not isinstance(raw_step, dict):
                continue
            alias = raw_step.get("alias") or f"step_{index + 1}"
            case_identifier: str | None = None
            base_inputs: dict[str, Any] = {}
            base_assertions: list[dict[str, Any]] = []

            case_reference = raw_step.get("case_id")
            if case_reference:
                case_uuid = uuid.UUID(str(case_reference))
                case = _get_case(session, case_cache, case_uuid, project_uuid)
                base_inputs = deepcopy(case.inputs or {})
                base_assertions = _coerce_assertions(case.assertions)
                case_identifier = str(case.id)

            override_inputs = raw_step.get("inputs") if isinstance(raw_step.get("inputs"), dict) else {}
            merged_inputs = _merge_inputs(base_inputs, override_inputs)

            step_variables = raw_step.get("variables")
            if isinstance(step_variables, dict):
                rendered_vars = render_value(step_variables, context)
                if isinstance(rendered_vars, dict):
                    context.variables.update(rendered_vars)

            step_assertions = _coerce_assertions(raw_step.get("assertions"))
            merged_assertions = base_assertions.copy()
            if step_assertions:
                merged_assertions.extend(step_assertions)
            if not merged_assertions:
                merged_assertions = base_assertions

            attempts = 0
            result = None
            while attempts < NETWORK_RETRY_ATTEMPTS:
                attempts += 1
                try:
                    result = runner.execute(merged_inputs, context)
                    break
                except HttpRunnerError as exc:
                    if attempts >= NETWORK_RETRY_ATTEMPTS:
                        logger.error(
                            "suite_step_network_error",
                            suite_id=str(suite_uuid),
                            alias=alias,
                            error=str(exc),
                        )
                        _record_step_error(
                            request_steps,
                            response_steps,
                            assertion_steps,
                            metric_steps,
                            alias,
                            case_identifier,
                            exc,
                        )
                        total_duration += exc.metrics.get("duration_ms") or 0
                        total_response_size += exc.metrics.get("response_size") or 0
                        overall_passed = False
                        overall_error = str(exc)
                        break
                    delay = min(BACKOFF_BASE_SECONDS ** attempts, MAX_BACKOFF_DELAY_SECONDS)
                    logger.warning(
                        "suite_runner_retry",
                        suite_id=str(suite_uuid),
                        alias=alias,
                        attempt=attempts,
                        delay_seconds=delay,
                        error=str(exc),
                    )
                    time.sleep(delay)
            if result is None:
                break

            request_steps.append({
                "alias": alias,
                "case_id": case_identifier,
                "request": result.request_payload,
            })
            response_steps.append({
                "alias": alias,
                "case_id": case_identifier,
                "response": result.response_payload,
            })

            step_passed, assertion_results = assertion_engine.evaluate(merged_assertions, result.context_data, context)
            assertion_steps.append(
                {
                    "alias": alias,
                    "case_id": case_identifier,
                    "passed": step_passed,
                    "assertions": [item.to_dict() for item in assertion_results],
                }
            )

            step_metrics = {
                "alias": alias,
                "case_id": case_identifier,
                "duration_ms": result.metrics.get("duration_ms"),
                "status": result.metrics.get("status"),
                "response_size": result.metrics.get("response_size"),
            }
            metric_steps.append(step_metrics)
            total_duration += result.metrics.get("duration_ms") or 0
            total_response_size += result.metrics.get("response_size") or 0

            if not step_passed:
                overall_passed = False

            context.remember_step(alias, result.context_data)

        finished_at = datetime.now(timezone.utc)
        if overall_error:
            final_status = ReportStatus.ERROR
        elif overall_passed:
            final_status = ReportStatus.PASSED
        else:
            final_status = ReportStatus.FAILED

        assertions_payload: dict[str, Any] = {
            "passed": final_status == ReportStatus.PASSED,
            "steps": assertion_steps,
        }
        if overall_error:
            assertions_payload["error"] = overall_error

        metrics_payload = {
            "duration_ms": total_duration,
            "response_size": total_response_size,
            "status": "error" if final_status == ReportStatus.ERROR else "completed",
            "steps": metric_steps,
        }
        metrics_payload = _merge_dicts(metrics_payload, {"task_id": self.request.id})

        report.status = final_status
        report.finished_at = finished_at
        report.duration_ms = total_duration
        report.request_payload = {"steps": request_steps}
        report.response_payload = {"steps": response_steps}
        report.assertions_result = assertions_payload
        report.metrics = _merge_dicts(report.metrics, metrics_payload)
        session.add(report)
        session.commit()

    except Exception as exc:  # pragma: no cover - unexpected safeguard
        session.rollback()
        logger.error("execute_suite_error", report_id=report_id, error=str(exc))
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
        raise ValueError("Test report not found for suite execution task")
    return report


def _get_suite(session: Session, suite_id: uuid.UUID, project_id: uuid.UUID) -> TestSuite:
    stmt = (
        select(TestSuite)
        .where(
            TestSuite.id == suite_id,
            TestSuite.project_id == project_id,
            TestSuite.is_deleted.is_(False),
        )
        .limit(1)
    )
    suite = session.execute(stmt).scalar_one_or_none()
    if suite is None:
        raise ValueError("Test suite not found for execution task")
    return suite


def _get_case(
    session: Session,
    cache: dict[uuid.UUID, TestCase],
    case_id: uuid.UUID,
    project_id: uuid.UUID,
) -> TestCase:
    if case_id in cache:
        return cache[case_id]
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
        raise ValueError("Referenced test case not found for suite execution")
    cache[case_id] = case
    return case


def _mark_report_running(session: Session, report: TestReport, task_id: str) -> None:
    report.status = ReportStatus.RUNNING
    report.started_at = datetime.now(timezone.utc)
    report.metrics = _merge_dicts(report.metrics, {"task_id": task_id})
    session.add(report)
    session.commit()


def _record_step_error(
    request_steps: list[dict[str, Any]],
    response_steps: list[dict[str, Any]],
    assertion_steps: list[dict[str, Any]],
    metric_steps: list[dict[str, Any]],
    alias: str,
    case_identifier: str | None,
    error: HttpRunnerError,
) -> None:
    request_steps.append(
        {
            "alias": alias,
            "case_id": case_identifier,
            "request": error.request_payload,
        }
    )
    response_steps.append(
        {
            "alias": alias,
            "case_id": case_identifier,
            "response": error.response_payload or {"error": str(error)},
        }
    )
    assertion_steps.append(
        {
            "alias": alias,
            "case_id": case_identifier,
            "passed": False,
            "error": str(error),
            "assertions": [],
        }
    )
    metric_steps.append(
        {
            "alias": alias,
            "case_id": case_identifier,
            "duration_ms": error.metrics.get("duration_ms"),
            "status": "error",
            "response_size": error.metrics.get("response_size", 0),
        }
    )


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


def _merge_inputs(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            nested = deepcopy(merged.get(key))
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = value
    return merged


def _coerce_assertions(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        items = value.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        return [
            {"operator": str(key), "expected": val}
            for key, val in value.items()
            if key != "items"
        ]
    return []


def _merge_dicts(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    payload = dict(base or {})
    payload.update(updates)
    return payload
