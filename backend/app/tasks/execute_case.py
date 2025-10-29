from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.celery import celery_app
from app.core.config import get_settings
from app.core.http import get_http_client
from app.db.session import SessionLocal
from app.logging import bind_log_context, get_logger, unbind_log_context
from app.models import Dataset, Environment, ReportEntityType, ReportStatus, TestCase, TestReport
from app.observability import track_task
from app.observability.metrics import (
    record_circuit_breaker_event,
    record_execution_retry,
    record_rate_limit_throttle,
)
from app.services.assertions.engine import AssertionEngine
from app.services.datasets.loader import DatasetLoadError, load_dataset_rows
from app.services.execution.context import ExecutionContext
from app.services.execution.parameterization import ParameterizationEngine, ParameterizationError
from app.services.execution.policy import ExecutionPolicySnapshot, snapshot_from_dict
from app.services.execution.runtime import ExecutionPolicyRuntime
from app.services.notify.dispatcher import queue_run_finished_notifications
from app.services.reports.progress import publish_progress_event
from app.services.runner.http_runner import HttpRunner, HttpRunnerError

logger = get_logger()

assertion_engine = AssertionEngine()
parameterization_engine = ParameterizationEngine()
STEP_ALIAS = "case"


def get_http_runner(policy: ExecutionPolicySnapshot | None = None) -> HttpRunner:
    settings = get_settings()
    timeout = httpx.Timeout(
        connect=settings.httpx_connect_timeout,
        read=settings.httpx_read_timeout,
        write=settings.httpx_write_timeout,
        pool=settings.httpx_pool_timeout,
    )
    timeout_seconds = policy.timeout_seconds if policy is not None else settings.request_timeout_seconds
    max_retries = policy.retry_max_attempts if policy is not None else settings.httpx_retry_attempts
    backoff_base = (
        policy.retry_backoff.base_seconds if policy is not None else settings.httpx_retry_backoff_factor
    )
    backoff_max = policy.retry_backoff.max_seconds if policy is not None else None
    jitter_ratio = policy.retry_backoff.jitter_ratio if policy is not None else 0.5
    return HttpRunner(
        timeout_seconds,
        settings.max_response_size_bytes,
        timeout=timeout,
        client=get_http_client(),
        max_retries=max_retries,
        retry_backoff_factor=backoff_base,
        retry_backoff_max=backoff_max,
        retry_jitter_ratio=jitter_ratio,
        retry_statuses=settings.httpx_retry_statuses,
        retry_methods=settings.httpx_retry_methods,
        redact_fields=settings.redact_fields,
        redaction_placeholder=settings.redaction_placeholder,
    )


@celery_app.task(name="app.tasks.execute_case.execute_test_case", bind=True, queue="cases")
def execute_test_case(self, report_id: str, case_id: str, project_id: str) -> None:
    settings = get_settings()
    session = SessionLocal()
    report_uuid = uuid.UUID(report_id)
    case_uuid = uuid.UUID(case_id)
    project_uuid = uuid.UUID(project_id)

    bind_log_context(report_id=report_id, project_id=project_id, task_id=getattr(self.request, "id", None))

    cm = track_task("execute_test_case", queue="cases", project_id=project_id)
    exc_info: tuple[Any, Any, Any] = (None, None, None)
    cm.__enter__()
    try:
        report = _get_report(session, report_uuid, project_uuid, ReportEntityType.CASE, case_uuid)
        case = _get_case(session, case_uuid, project_uuid)

        policy_snapshot = snapshot_from_dict(
            report.policy_snapshot if isinstance(report.policy_snapshot, dict) else None,
            settings=settings,
        )
        runtime = ExecutionPolicyRuntime(policy_snapshot)
        runner = get_http_runner(policy_snapshot)
        bind_log_context(policy_id=policy_snapshot.id or "default")

        _mark_report_running(session, report, self.request.id, policy_snapshot)

        publish_progress_event(
            report_id,
            "started",
            payload={
                "task_id": self.request.id,
                "entity_type": report.entity_type.value,
                "entity_id": str(report.entity_id),
                "policy": {"id": policy_snapshot.id, "name": policy_snapshot.name},
                "run_number": report.run_number,
            },
        )
        publish_progress_event(
            report_id,
            "step_progress",
            step_alias=STEP_ALIAS,
            payload={"status": "started", "attempt": 1},
        )

        context = ExecutionContext()
        max_attempts = max(1, policy_snapshot.retry_max_attempts)
        attempts = 0
        last_error: Exception | None = None
        result: Any | None = None
        assertion_details: list[dict[str, Any]] = []
        host = _extract_case_host(case.inputs)

        while attempts < max_attempts:
            attempts += 1
            breaker_wait = runtime.circuit_remaining(host or "")
            if breaker_wait > 0:
                record_circuit_breaker_event(policy_snapshot.id, host, "blocked")
                publish_progress_event(
                    report_id,
                    "step_progress",
                    step_alias=STEP_ALIAS,
                    payload={
                        "status": "blocked",
                        "attempt": attempts,
                        "retry_in_seconds": breaker_wait,
                        "message": "Circuit breaker open, waiting to retry",
                    },
                )
                if attempts >= max_attempts:
                    last_error = RuntimeError("Circuit breaker open")
                    break
                time.sleep(min(breaker_wait, runtime.backoff_delay(attempts)))
                continue

            with runtime.acquire_slot():
                rate_wait = runtime.rate_limit_delay(host or "")
                if rate_wait > 0:
                    record_rate_limit_throttle(policy_snapshot.id, host)
                    time.sleep(rate_wait)
                try:
                    result = runner.execute(case.inputs, context, project_id=project_id)
                except HttpRunnerError as exc:
                    last_error = exc
                    remaining, opened = runtime.record_failure(host or "")
                    will_retry = attempts < max_attempts
                    event_payload: dict[str, Any] = {
                        "status": "retrying" if will_retry else "error",
                        "attempt": attempts,
                        "message": str(exc),
                    }
                    if opened:
                        record_circuit_breaker_event(policy_snapshot.id, host, "opened")
                    if will_retry:
                        delay = runtime.backoff_delay(attempts)
                        if remaining > 0:
                            delay = max(delay, remaining)
                        event_payload["retry_in_seconds"] = delay
                        record_execution_retry(policy_snapshot.id, report.entity_type.value, "network")
                        publish_progress_event(
                            report_id,
                            "step_progress",
                            step_alias=STEP_ALIAS,
                            payload=event_payload,
                        )
                        time.sleep(delay)
                        continue
                    _mark_runner_error(
                        session,
                        report,
                        exc,
                        self.request.id,
                        retry_attempt=max(0, attempts - 1),
                    )
                    publish_progress_event(
                        report_id,
                        "step_progress",
                        step_alias=STEP_ALIAS,
                        payload=event_payload,
                    )
                    publish_progress_event(
                        report_id,
                        "finished",
                        payload={
                            "status": ReportStatus.ERROR.value,
                            "message": str(exc),
                        },
                    )
                    queue_run_finished_notifications(session, report)
                    return
            runtime.record_success(host or "")
            metrics_snapshot = _compact_metrics(result.metrics)
            metrics_snapshot["attempt"] = attempts
            publish_progress_event(
                report_id,
                "step_progress",
                step_alias=STEP_ALIAS,
                payload={
                    "status": "completed",
                    "attempt": attempts,
                    "metrics": metrics_snapshot,
                },
            )

            passed, assertion_results = assertion_engine.evaluate(case.assertions, result.context_data, context)
            assertion_details = [item.to_dict() for item in assertion_results]
            publish_progress_event(
                report_id,
                "assertion_result",
                step_alias=STEP_ALIAS,
                payload={
                    "passed": passed,
                    "results": _trim_assertions(assertion_details),
                },
            )
            if passed:
                break

            last_error = None
            if not policy_snapshot.retry_backoff.retry_on_assertions or attempts >= max_attempts:
                break

            delay = runtime.backoff_delay(attempts)
            record_execution_retry(policy_snapshot.id, report.entity_type.value, "assertion")
            publish_progress_event(
                report_id,
                "step_progress",
                step_alias=STEP_ALIAS,
                payload={
                    "status": "retrying",
                    "attempt": attempts,
                    "message": "Assertions failed, retrying",
                    "retry_in_seconds": delay,
                },
            )
            time.sleep(delay)

        report.retry_attempt = max(0, attempts - 1)
        if result is None:
            message = str(last_error) if last_error else "Execution failed"
            _mark_unexpected_error(
                session,
                report,
                message,
                self.request.id,
                retry_attempt=report.retry_attempt,
            )
            publish_progress_event(
                report_id,
                "finished",
                payload={
                    "status": ReportStatus.ERROR.value,
                    "message": message,
                },
            )
            queue_run_finished_notifications(session, report)
            return

        finished_at = datetime.now(timezone.utc)
        metrics = _merge_dicts(
            result.metrics,
            {
                "task_id": self.request.id,
                "attempts": attempts,
                "policy_id": policy_snapshot.id or "default",
            },
        )
        report.status = ReportStatus.PASSED if passed else ReportStatus.FAILED
        report.finished_at = finished_at
        report.duration_ms = result.metrics.get("duration_ms")
        report.request_payload = result.request_payload
        report.response_payload = result.response_payload
        report.assertions_result = {
            "passed": passed,
            "results": assertion_details,
        }
        report.metrics = metrics
        session.add(report)
        session.commit()

        publish_progress_event(
            report_id,
            "finished",
            payload={
                "status": report.status.value,
                "finished_at": finished_at.isoformat(),
                "duration_ms": report.duration_ms,
                "task_id": self.request.id,
                "attempts": attempts,
            },
        )
        queue_run_finished_notifications(session, report)

    except Exception as exc:  # pragma: no cover - unexpected safeguard
        exc_info = (type(exc), exc, exc.__traceback__)
        session.rollback()
        logger.error("execute_case_error", report_id=report_id, error=str(exc))
        report = session.get(TestReport, report_uuid)
        if report:
            _mark_unexpected_error(
                session,
                report,
                str(exc),
                self.request.id,
                retry_attempt=report.retry_attempt,
            )
            publish_progress_event(
                report_id,
                "finished",
                payload={
                    "status": ReportStatus.ERROR.value,
                    "message": str(exc),
                },
            )
            queue_run_finished_notifications(session, report)
        raise
    finally:
        cm.__exit__(*exc_info)
        unbind_log_context("report_id", "project_id", "task_id", "policy_id")
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


def _mark_report_running(
    session: Session,
    report: TestReport,
    task_id: str,
    policy_snapshot: ExecutionPolicySnapshot,
) -> None:
    report.status = ReportStatus.RUNNING
    report.started_at = datetime.now(timezone.utc)
    report.policy_snapshot = policy_snapshot.to_dict()
    report.metrics = _merge_dicts(
        report.metrics,
        {
            "task_id": task_id,
            "policy_id": policy_snapshot.id or "default",
            "policy_name": policy_snapshot.name,
        },
    )
    session.add(report)
    session.commit()


def _mark_runner_error(
    session: Session,
    report: TestReport,
    error: HttpRunnerError,
    task_id: str,
    *,
    retry_attempt: int | None = None,
) -> None:
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
    if retry_attempt is not None:
        report.retry_attempt = max(0, retry_attempt)
    metrics = _merge_dicts(error.metrics, {"task_id": task_id})
    if "status" not in metrics:
        metrics["status"] = "error"
    report.metrics = metrics
    session.add(report)
    session.commit()


def _mark_unexpected_error(
    session: Session,
    report: TestReport,
    message: str,
    task_id: str,
    *,
    retry_attempt: int | None = None,
) -> None:
    finished_at = datetime.now(timezone.utc)
    report.status = ReportStatus.ERROR
    report.finished_at = finished_at
    report.assertions_result = {
        "passed": False,
        "results": [],
        "error": message,
    }
    if retry_attempt is not None:
        report.retry_attempt = max(0, retry_attempt)
    report.metrics = _merge_dicts(report.metrics, {"task_id": task_id, "status": "error"})
    session.add(report)
    session.commit()


def _extract_case_host(inputs: dict[str, Any]) -> str | None:
    if not isinstance(inputs, dict):
        return None
    url_value = inputs.get("url")
    if isinstance(url_value, str) and url_value:
        parsed = urlparse(url_value)
        if parsed.netloc:
            return parsed.netloc
        if parsed.path:
            return parsed.path
    return None


def _compact_metrics(metrics: dict[str, Any] | None) -> dict[str, Any]:
    if not metrics:
        return {}
    compact: dict[str, Any] = {}
    for key in ("duration_ms", "status", "response_size"):
        value = metrics.get(key)
        if value is not None:
            compact[key] = value
    return compact


def _trim_assertions(results: list[dict[str, Any]], limit: int = 25) -> list[dict[str, Any]]:
    if len(results) <= limit:
        return results
    trimmed = results[:limit]
    trimmed.append({"info": f"{len(results) - limit} additional assertions truncated"})
    return trimmed


def _merge_dicts(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    payload = dict(base or {})
    payload.update(updates)
    return payload
