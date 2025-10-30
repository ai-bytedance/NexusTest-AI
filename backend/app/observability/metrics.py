from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from sqlalchemy import event
from sqlalchemy.engine import Engine
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings

_settings = get_settings()
_NAMESPACE = _settings.metrics_namespace

_REQUEST_LABELS = ("method", "endpoint", "status", "project_id")
_IN_PROGRESS_LABELS = ("method", "endpoint", "project_id")
_EXTERNAL_HTTP_LABELS = ("target", "method", "status", "project_id")
_TASK_LABELS = ("task", "queue", "project_id")
_TASK_STATUS_LABELS = (*_TASK_LABELS, "status")
_TASK_FAILURE_LABELS = (*_TASK_LABELS, "reason")
_TASK_RETRY_LABELS = ("task", "queue", "reason")
_EXECUTION_RETRY_LABELS = ("policy", "entity_type", "reason")
_EXECUTION_THROTTLE_LABELS = ("policy", "host")
_EXECUTION_CIRCUIT_LABELS = ("policy", "host", "event")
_NOTIFICATION_LABELS = ("provider",)
_AI_TASK_LABELS = ("provider", "model", "status", "task_type", "project_id")
_AI_TOKEN_LABELS = ("provider", "model", "token_type", "task_type", "project_id")

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total number of HTTP requests handled by FastAPI",
    _REQUEST_LABELS,
    namespace=_NAMESPACE,
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Latency for FastAPI HTTP requests",
    _REQUEST_LABELS,
    namespace=_NAMESPACE,
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
REQUEST_IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "Currently active FastAPI HTTP requests",
    _IN_PROGRESS_LABELS,
    namespace=_NAMESPACE,
)
DB_QUERY_DURATION = Histogram(
    "db_query_duration_seconds",
    "SQLAlchemy database query latency",
    ("operation",),
    namespace=_NAMESPACE,
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5),
)
EXTERNAL_HTTP_DURATION = Histogram(
    "external_http_request_duration_seconds",
    "Duration for outbound HTTP calls performed by execution runners",
    _EXTERNAL_HTTP_LABELS,
    namespace=_NAMESPACE,
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
NOTIFICATION_SENT = Counter(
    "notification_sent_total",
    "Count of successfully delivered notifications",
    _NOTIFICATION_LABELS,
    namespace=_NAMESPACE,
)
NOTIFICATION_FAILED = Counter(
    "notification_failed_total",
    "Count of notifications that permanently failed",
    _NOTIFICATION_LABELS,
    namespace=_NAMESPACE,
)
TASK_DURATION = Histogram(
    "celery_task_duration_seconds",
    "Celery task execution duration in seconds",
    _TASK_LABELS,
    namespace=_NAMESPACE,
    buckets=(0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600),
)
TASK_EXECUTIONS = Counter(
    "celery_task_executions_total",
    "Total Celery task executions partitioned by outcome",
    _TASK_STATUS_LABELS,
    namespace=_NAMESPACE,
)
TASK_FAILURE_REASONS = Counter(
    "celery_task_failure_total",
    "Celery task failures by reason",
    _TASK_FAILURE_LABELS,
    namespace=_NAMESPACE,
)
TASK_RETRIES = Counter(
    "celery_task_retries_total",
    "Celery task retries grouped by reason",
    _TASK_RETRY_LABELS,
    namespace=_NAMESPACE,
)
EXECUTION_RETRIES = Counter(
    "execution_retries_total",
    "Execution retries initiated under policy control",
    _EXECUTION_RETRY_LABELS,
    namespace=_NAMESPACE,
)
EXECUTION_RATE_LIMIT_THROTTLES = Counter(
    "execution_rate_limit_throttles_total",
    "Number of rate limit throttles enforced per host",
    _EXECUTION_THROTTLE_LABELS,
    namespace=_NAMESPACE,
)
EXECUTION_CIRCUIT_EVENTS = Counter(
    "execution_circuit_breaker_events_total",
    "Circuit breaker events recorded per host",
    _EXECUTION_CIRCUIT_LABELS,
    namespace=_NAMESPACE,
)
TASK_QUEUE_LENGTH = Gauge(
    "celery_queue_length",
    "Approximate length of Celery broker queues",
    ("queue",),
    namespace=_NAMESPACE,
)
AI_TASK_COUNT = Counter(
    "ai_tasks_total",
    "Total AI related tasks executed",
    _AI_TASK_LABELS,
    namespace=_NAMESPACE,
)
AI_REQUEST_DURATION = Histogram(
    "ai_request_duration_seconds",
    "Duration of AI provider invocations",
    _AI_TASK_LABELS,
    namespace=_NAMESPACE,
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)
AI_TOKEN_USAGE = Counter(
    "ai_tokens_used_total",
    "Tokens consumed by AI requests partitioned by token type",
    _AI_TOKEN_LABELS,
    namespace=_NAMESPACE,
)


def _metrics_enabled() -> bool:
    return get_settings().metrics_enabled


def _normalize_endpoint(path: str) -> str:
    candidate = path or "unknown"
    return candidate if len(candidate) <= 120 else f"{candidate[:117]}…"


def _normalize_status(value: int | str) -> str:
    if isinstance(value, int):
        return str(value)
    candidate = str(value).strip()
    return candidate or "unknown"


def _normalize_project_id(raw: str | None) -> str:
    if raw is None:
        return "unknown"
    candidate = str(raw).strip()
    if not candidate:
        return "unknown"
    try:
        parsed = uuid.UUID(candidate)
        return str(parsed)
    except ValueError:
        return candidate[:64] if candidate else "unknown"


def _normalize_queue(queue: str | None) -> str:
    return (queue or "default").strip() or "default"


def _normalize_reason(reason: str | None) -> str:
    if not reason:
        return "unknown"
    sanitized = reason.strip().lower().replace(" ", "_")
    return sanitized[:64] if sanitized else "unknown"


def _normalize_provider(provider: str | None) -> str:
    if not provider:
        return "unknown"
    sanitized = provider.strip().lower()
    if not sanitized:
        return "unknown"
    return sanitized[:64]


def _normalize_policy_id(policy_id: str | None) -> str:
    if not policy_id:
        return "default"
    candidate = str(policy_id).strip()
    if not candidate:
        return "default"
    return candidate[:64]


def _normalize_host(host: str | None) -> str:
    if not host:
        return "unknown"
    sanitized = host.strip().lower()
    if not sanitized:
        return "unknown"
    return sanitized[:120]


def _extract_project_id(request: Request) -> str:
    candidate = request.path_params.get("project_id") if request.path_params else None
    if not candidate:
        candidate = request.headers.get("X-Project-ID") or request.headers.get("X-Project-Id")
    return _normalize_project_id(candidate)


def _classify_db_operation(statement: str) -> str:
    first = (statement or "").lstrip().split(" ", 1)[0].upper()
    if not first:
        return "OTHER"
    if first in {"SELECT", "INSERT", "UPDATE", "DELETE", "COMMIT", "ROLLBACK"}:
        return first
    return "OTHER"


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        settings = get_settings()
        if not settings.metrics_enabled or request.url.path.startswith("/metrics"):
            return await call_next(request)

        start = time.perf_counter()
        endpoint = _normalize_endpoint(getattr(getattr(request.scope.get("route"), "path", None), "strip", lambda: request.url.path)())
        method = request.method.upper()
        project_id = _extract_project_id(request)
        in_progress_labels = {
            "method": method,
            "endpoint": endpoint,
            "project_id": project_id,
        }

        REQUEST_IN_PROGRESS.labels(**in_progress_labels).inc()
        try:
            response = await call_next(request)
            status_label = _normalize_status(response.status_code)
            return response
        except Exception:
            status_label = "500"
            raise
        finally:
            duration = time.perf_counter() - start
            labels = {
                "method": method,
                "endpoint": endpoint,
                "status": status_label,
                "project_id": project_id,
            }
            REQUEST_COUNT.labels(**labels).inc()
            REQUEST_LATENCY.labels(**labels).observe(duration)
            REQUEST_IN_PROGRESS.labels(**in_progress_labels).dec()


def track_external_http_call(target: str, method: str, status_code: int, project_id: str | None, duration: float) -> None:
    if not _metrics_enabled():
        return
    labels = {
        "target": (target or "unknown")[:120] or "unknown",
        "method": method.upper(),
        "status": _normalize_status(status_code),
        "project_id": _normalize_project_id(project_id),
    }
    EXTERNAL_HTTP_DURATION.labels(**labels).observe(max(duration, 0.0))


def record_notification_sent(provider: str | None) -> None:
    if not _metrics_enabled():
        return
    NOTIFICATION_SENT.labels(provider=_normalize_provider(provider)).inc()


def record_notification_failed(provider: str | None) -> None:
    if not _metrics_enabled():
        return
    NOTIFICATION_FAILED.labels(provider=_normalize_provider(provider)).inc()


def instrument_engine(engine: Engine) -> None:
    if getattr(engine, "_metrics_instrumented", False):
        return

    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # type: ignore[override]
        if not _metrics_enabled():
            return
        stack = conn.info.setdefault("_metrics_query_start", [])
        stack.append((time.perf_counter(), _classify_db_operation(statement)))

    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # type: ignore[override]
        if not _metrics_enabled():
            conn.info.pop("_metrics_query_start", None)
            return
        stack = conn.info.get("_metrics_query_start")
        if not stack:
            return
        start, operation = stack.pop()
        duration = time.perf_counter() - start
        DB_QUERY_DURATION.labels(operation=operation).observe(max(duration, 0.0))

    engine._metrics_instrumented = True  # type: ignore[attr-defined]


@contextmanager
def track_task(task_name: str, *, queue: str | None = None, project_id: str | None = None):
    settings = get_settings()
    start = time.perf_counter()
    failure_reason: str | None = None
    try:
        yield
    except Exception as exc:
        failure_reason = exc.__class__.__name__ or exc.__class__.__qualname__ or "error"
        raise
    finally:
        if not settings.metrics_enabled:
            return
        duration = time.perf_counter() - start
        labels = {
            "task": task_name,
            "queue": _normalize_queue(queue),
            "project_id": _normalize_project_id(project_id),
        }
        TASK_DURATION.labels(**labels).observe(max(duration, 0.0))
        status_labels = {**labels, "status": "failure" if failure_reason else "success"}
        TASK_EXECUTIONS.labels(**status_labels).inc()
        if failure_reason:
            reason_label = _normalize_reason(failure_reason)
            TASK_FAILURE_REASONS.labels(**{**labels, "reason": reason_label}).inc()


def record_task_retry(task_name: str, queue: str | None, reason: str | None) -> None:
    if not _metrics_enabled():
        return
    TASK_RETRIES.labels(
        task=task_name,
        queue=_normalize_queue(queue),
        reason=_normalize_reason(reason or "retry"),
    ).inc()


def record_execution_retry(policy_id: str | None, entity_type: str | None, reason: str | None) -> None:
    if not _metrics_enabled():
        return
    EXECUTION_RETRIES.labels(
        policy=_normalize_policy_id(policy_id),
        entity_type=(entity_type or "unknown").strip().lower() or "unknown",
        reason=_normalize_reason(reason or "retry"),
    ).inc()


def record_rate_limit_throttle(policy_id: str | None, host: str | None) -> None:
    if not _metrics_enabled():
        return
    EXECUTION_RATE_LIMIT_THROTTLES.labels(
        policy=_normalize_policy_id(policy_id),
        host=_normalize_host(host),
    ).inc()


def record_circuit_breaker_event(policy_id: str | None, host: str | None, event: str | None) -> None:
    if not _metrics_enabled():
        return
    EXECUTION_CIRCUIT_EVENTS.labels(
        policy=_normalize_policy_id(policy_id),
        host=_normalize_host(host),
        event=_normalize_reason(event or "event"),
    ).inc()


def record_queue_length(queue: str, length: int) -> None:
    if not _metrics_enabled():
        return
    TASK_QUEUE_LENGTH.labels(queue=_normalize_queue(queue)).set(max(length, 0))


def observe_ai_call(
    *,
    provider: str,
    model: str | None,
    status: str,
    task_type: str,
    project_id: str | None,
    duration: float,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
) -> None:
    if not _metrics_enabled():
        return

    sanitized_provider = (provider or "unknown").strip() or "unknown"
    sanitized_model = (model or "unknown").strip() or "unknown"
    sanitized_status = (status or "unknown").strip() or "unknown"
    sanitized_task = (task_type or "unknown").strip() or "unknown"
    labels = {
        "provider": sanitized_provider,
        "model": sanitized_model,
        "status": sanitized_status,
        "task_type": sanitized_task,
        "project_id": _normalize_project_id(project_id),
    }
    AI_TASK_COUNT.labels(**labels).inc()
    AI_REQUEST_DURATION.labels(**labels).observe(max(duration, 0.0))

    token_labels = {
        "provider": sanitized_provider,
        "model": sanitized_model,
        "task_type": sanitized_task,
        "project_id": _normalize_project_id(project_id),
    }
    if prompt_tokens is not None:
        AI_TOKEN_USAGE.labels(**{**token_labels, "token_type": "prompt"}).inc(max(prompt_tokens, 0))
    if completion_tokens is not None:
        AI_TOKEN_USAGE.labels(**{**token_labels, "token_type": "completion"}).inc(max(completion_tokens, 0))
    if total_tokens is not None:
        AI_TOKEN_USAGE.labels(**{**token_labels, "token_type": "total"}).inc(max(total_tokens, 0))


def metrics_response() -> Response:
    payload = generate_latest()
    return Response(payload, media_type=CONTENT_TYPE_LATEST)


__all__ = [
    "MetricsMiddleware",
    "instrument_engine",
    "metrics_response",
    "track_task",
    "track_external_http_call",
    "observe_ai_call",
    "record_queue_length",
    "record_task_retry",
    "record_execution_retry",
    "record_rate_limit_throttle",
    "record_circuit_breaker_event",
    "REQUEST_COUNT",
    "REQUEST_LATENCY",
    "REQUEST_IN_PROGRESS",
    "TASK_DURATION",
    "TASK_EXECUTIONS",
    "TASK_FAILURE_REASONS",
    "TASK_RETRIES",
    "EXECUTION_RETRIES",
    "EXECUTION_RATE_LIMIT_THROTTLES",
    "EXECUTION_CIRCUIT_EVENTS",
    "TASK_QUEUE_LENGTH",
    "AI_TASK_COUNT",
    "AI_REQUEST_DURATION",
    "AI_TOKEN_USAGE",
]
