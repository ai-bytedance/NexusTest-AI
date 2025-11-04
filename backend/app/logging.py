import logging
import sys
from typing import Any, Awaitable, Callable
from uuid import uuid4

import structlog
from structlog import contextvars
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings

MAX_LOG_VALUE_LENGTH = 2048
TRUNCATION_SUFFIX = "...(truncated)"
_MAX_MASK_DEPTH = 4


def _truncate_large_values(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key, value in list(event_dict.items()):
        if isinstance(value, str) and len(value) > MAX_LOG_VALUE_LENGTH:
            event_dict[key] = f"{value[:MAX_LOG_VALUE_LENGTH]}{TRUNCATION_SUFFIX}"
        elif isinstance(value, (bytes, bytearray)):
            decoded = bytes(value).decode("utf-8", errors="replace")
            if len(decoded) > MAX_LOG_VALUE_LENGTH:
                event_dict[key] = f"{decoded[:MAX_LOG_VALUE_LENGTH]}{TRUNCATION_SUFFIX}"
        elif isinstance(value, list):
            event_dict[key] = [
                item if not isinstance(item, str) or len(item) <= MAX_LOG_VALUE_LENGTH else f"{item[:MAX_LOG_VALUE_LENGTH]}{TRUNCATION_SUFFIX}"
                for item in value
            ]
    return event_dict


def _mask_sensitive_values(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    redacted_keys = {entry.lower() for entry in settings.redact_fields}
    placeholder = settings.redaction_placeholder

    def _mask(value: Any, depth: int = 0) -> Any:
        if depth > _MAX_MASK_DEPTH:
            return value
        if isinstance(value, dict):
            for key, item in list(value.items()):
                lowered = key.lower() if isinstance(key, str) else None
                if lowered and lowered in redacted_keys:
                    value[key] = placeholder
                    continue
                value[key] = _mask(item, depth + 1)
            return value
        if isinstance(value, list):
            return [_mask(item, depth + 1) for item in value]
        if isinstance(value, tuple):
            return tuple(_mask(item, depth + 1) for item in value)
        if isinstance(value, set):
            return {_mask(item, depth + 1) for item in value}
        if isinstance(value, (bytes, bytearray)) and "authorization" in redacted_keys:
            return placeholder
        return value

    return _mask(event_dict)


def _extract_trace_id(traceparent: str | None) -> str | None:
    if not traceparent:
        return None
    parts = traceparent.split("-")
    if len(parts) < 2:
        return None
    trace_id = parts[1].strip()
    if len(trace_id) != 32:
        return None
    return trace_id


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(sys.stdout)], format="%(message)s")
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(logger_name).handlers = []

    structlog.configure(
        processors=[
            contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _mask_sensitive_values,
            _truncate_large_values,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def bind_log_context(**params: Any) -> None:
    payload = {key: str(value) for key, value in params.items() if value is not None}
    if payload:
        contextvars.bind_contextvars(**payload)


def unbind_log_context(*keys: str) -> None:
    for key in keys:
        try:
            contextvars.unbind_contextvars(key)
        except KeyError:
            continue


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:  # type: ignore[override]
        settings = get_settings()
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        traceparent = request.headers.get("traceparent")
        trace_id = _extract_trace_id(traceparent) if settings.otel_trace_propagation_enabled else None

        contextvars.clear_contextvars()
        bind_log_context(request_id=request_id, path=str(request.url.path))
        if trace_id:
            bind_log_context(trace_id=trace_id)

        try:
            response = await call_next(request)
        finally:
            if trace_id:
                unbind_log_context("trace_id")

        response.headers["X-Request-ID"] = request_id
        if traceparent and settings.otel_trace_propagation_enabled:
            response.headers.setdefault("Traceparent", traceparent)
        return response


def get_logger(name: str | None = None, **initial_values: Any) -> structlog.stdlib.BoundLogger:
    if name is not None:
        return structlog.get_logger(name, **initial_values)
    return structlog.get_logger(**initial_values)


__all__ = [
    "RequestIdMiddleware",
    "bind_log_context",
    "configure_logging",
    "get_logger",
    "unbind_log_context",
]
