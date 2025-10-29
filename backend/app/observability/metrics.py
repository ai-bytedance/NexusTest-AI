from __future__ import annotations

import time
from contextlib import contextmanager

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings
from app.logging import get_logger

_settings = get_settings()
_NAMESPACE = _settings.metrics_namespace

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ("method", "route", "status_code"),
    namespace=_NAMESPACE,
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ("method", "route", "status_code"),
    namespace=_NAMESPACE,
)
TASK_DURATION = Histogram(
    "celery_task_duration_seconds",
    "Celery task execution duration in seconds",
    ("task",),
    namespace=_NAMESPACE,
)
TASK_SUCCESS = Counter(
    "celery_task_success_total",
    "Total number of successful Celery task executions",
    ("task",),
    namespace=_NAMESPACE,
)
TASK_FAILURE = Counter(
    "celery_task_failure_total",
    "Total number of failed Celery task executions",
    ("task",),
    namespace=_NAMESPACE,
)

_logger = get_logger().bind(component="metrics")


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        # Avoid expensive operations if metrics are disabled or when scraping.
        settings = get_settings()
        if not settings.metrics_enabled or request.url.path.startswith("/metrics"):
            return await call_next(request)

        start = time.perf_counter()
        route_path = request.url.path
        route = request.scope.get("route")
        if route is not None:
            route_path = getattr(route, "path", route_path)

        try:
            response = await call_next(request)
        except Exception:
            duration = time.perf_counter() - start
            labels = {
                "method": request.method.upper(),
                "route": route_path,
                "status_code": "500",
            }
            REQUEST_COUNT.labels(**labels).inc()
            REQUEST_LATENCY.labels(**labels).observe(duration)
            raise
        else:
            duration = time.perf_counter() - start
            labels = {
                "method": request.method.upper(),
                "route": route_path,
                "status_code": str(response.status_code),
            }
            REQUEST_COUNT.labels(**labels).inc()
            REQUEST_LATENCY.labels(**labels).observe(duration)
            return response


@contextmanager
def track_task(task_name: str):
    settings = get_settings()
    start = time.perf_counter()
    failed = False
    try:
        yield
    except Exception:
        failed = True
        raise
    finally:
        if settings.metrics_enabled:
            duration = time.perf_counter() - start
            TASK_DURATION.labels(task=task_name).observe(duration)
            if failed:
                TASK_FAILURE.labels(task=task_name).inc()
            else:
                TASK_SUCCESS.labels(task=task_name).inc()


def metrics_response() -> Response:
    payload = generate_latest()
    return Response(payload, media_type=CONTENT_TYPE_LATEST)


__all__ = [
    "MetricsMiddleware",
    "metrics_response",
    "track_task",
    "REQUEST_COUNT",
    "REQUEST_LATENCY",
    "TASK_DURATION",
    "TASK_SUCCESS",
    "TASK_FAILURE",
]
