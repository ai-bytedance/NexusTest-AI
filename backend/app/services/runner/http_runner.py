from __future__ import annotations

import re
import time
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Sequence, cast
from urllib.parse import urlparse

import httpx

from app.core.http import get_http_client
from app.logging import get_logger
from app.observability.metrics import track_external_http_call
from app.services.execution.context import ExecutionContext, render_value

_MAX_RETRY_DELAY_SECONDS = 30.0
_SECRET_TEMPLATE_PATTERN = re.compile(r"{{\s*secret\.[^{}]+}}", re.IGNORECASE)


@dataclass
class HttpRunnerResult:
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    metrics: dict[str, Any]
    context_data: dict[str, Any]


class HttpRunnerError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        request_payload: dict[str, Any],
        metrics: dict[str, Any],
        response_payload: dict[str, Any] | None = None,
        original: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.request_payload = request_payload
        self.metrics = metrics
        self.response_payload = response_payload or {}
        self.original = original


class HttpRunner:
    def __init__(
        self,
        timeout_seconds: float,
        max_response_size_bytes: int,
        *,
        timeout: httpx.Timeout | None = None,
        client: httpx.Client | None = None,
        max_retries: int = 3,
        retry_backoff_factor: float = 0.5,
        retry_statuses: Sequence[int] | None = None,
        retry_methods: Sequence[str] | None = None,
        redact_fields: Sequence[str] | None = None,
        redaction_placeholder: str = "***",
    ) -> None:
        self._timeout = timeout or httpx.Timeout(timeout_seconds)
        self._max_response_size_bytes = max_response_size_bytes
        self._client = client
        self._max_retries = max(1, int(max_retries))
        self._retry_backoff_factor = max(0.1, float(retry_backoff_factor))
        self._retry_statuses = {int(status) for status in (retry_statuses or [429, 500, 502, 503, 504])}
        default_methods = retry_methods or ["GET", "HEAD", "OPTIONS", "PUT", "DELETE", "POST", "PATCH"]
        self._retry_methods = {method.upper() for method in default_methods if method}
        self._redact_fields = {field.lower() for field in (redact_fields or []) if isinstance(field, str)}
        self._redaction_placeholder = redaction_placeholder or "***"
        self._logger = get_logger().bind(component="http_runner")

    def execute(
        self,
        inputs: dict[str, Any],
        context: ExecutionContext | None = None,
        *,
        project_id: str | None = None,
        prepared_inputs: dict[str, Any] | None = None,
        display_inputs: dict[str, Any] | None = None,
    ) -> HttpRunnerResult:
        active_context = context or ExecutionContext()
        actual_inputs = prepared_inputs if prepared_inputs is not None else render_value(inputs, active_context)
        if not isinstance(actual_inputs, dict):
            raise ValueError("HTTP runner requires input payload to be an object")

        secret_values = _collect_secret_values(active_context)

        record_source: dict[str, Any] = {}
        if isinstance(display_inputs, dict):
            record_source = deepcopy(display_inputs)
        elif isinstance(inputs, dict):
            record_source = deepcopy(inputs)

        sanitized_inputs = _sanitize_payload(record_source, self._redact_fields, self._redaction_placeholder, secret_values)
        display_mapping = sanitized_inputs if isinstance(sanitized_inputs, dict) else {}

        method = str(actual_inputs.get("method", "GET")).upper()
        url_value = actual_inputs.get("url")
        if not isinstance(url_value, str) or not url_value:
            raise ValueError("HTTP runner requires a non-empty URL")

        display_url = display_mapping.get("url") if isinstance(display_mapping, dict) else None
        request_url = display_url if isinstance(display_url, str) and display_url else url_value

        headers = _normalize_mapping(actual_inputs.get("headers"))
        display_headers = _normalize_mapping(display_mapping.get("headers")) if isinstance(display_mapping, dict) else {}
        params = _normalize_mapping(actual_inputs.get("params"))
        display_params = _normalize_mapping(display_mapping.get("params")) if isinstance(display_mapping, dict) else {}

        request_payload: dict[str, Any] = {
            "method": method,
            "url": request_url,
        }
        if display_headers:
            request_payload["headers"] = display_headers
        elif headers:
            request_payload["headers"] = headers
        if display_params:
            request_payload["params"] = display_params
        elif params:
            request_payload["params"] = params

        request_kwargs: dict[str, Any] = {}
        if headers:
            request_kwargs["headers"] = headers
        if params:
            request_kwargs["params"] = params

        if "json" in actual_inputs:
            actual_json = actual_inputs.get("json")
            request_kwargs["json"] = actual_json
            display_json = display_mapping.get("json") if isinstance(display_mapping, dict) else None
            request_payload["json"] = display_json if display_json is not None else actual_json
        elif "body" in actual_inputs:
            body = actual_inputs.get("body")
            display_body = display_mapping.get("body") if isinstance(display_mapping, dict) else None
            if isinstance(body, (dict, list)):
                request_kwargs["json"] = body
                request_payload["json"] = display_body if isinstance(display_body, (dict, list)) else body
            elif body is not None:
                if isinstance(body, (bytes, bytearray)):
                    content_bytes = bytes(body)
                    display_body_text = (
                        display_body
                        if isinstance(display_body, str)
                        else content_bytes.decode("utf-8", errors="replace")
                    )
                else:
                    body_text = str(body)
                    content_bytes = body_text.encode("utf-8")
                    display_body_text = str(display_body) if isinstance(display_body, str) else body_text
                request_kwargs["content"] = content_bytes
                truncated_body, is_truncated, note = _truncate_text(display_body_text, self._max_response_size_bytes)
                body_payload = {"text": truncated_body, "truncated": is_truncated}
                if note:
                    body_payload["note"] = note
                request_payload["body"] = body_payload

        request_payload_record = cast(
            dict[str, Any],
            _sanitize_payload(deepcopy(request_payload), self._redact_fields, self._redaction_placeholder, secret_values),
        )

        parsed_target = urlparse(url_value)
        target_label = parsed_target.netloc or parsed_target.path or url_value

        timeout = self._timeout
        client = self._client or get_http_client()

        attempts = 0
        last_exception: Exception | None = None
        response: httpx.Response | None = None
        overall_start = time.perf_counter()

        while attempts < self._max_retries:
            attempts += 1
            try:
                response = client.request(method, url_value, timeout=timeout, **request_kwargs)
            except httpx.TimeoutException as exc:
                last_exception = exc
                self._logger.warning(
                    "http_runner_timeout",
                    attempt=attempts,
                    url=url_value,
                    method=method,
                )
                if attempts >= self._max_retries:
                    break
                delay = self._backoff_delay(attempts)
                if delay > 0:
                    time.sleep(delay)
                continue
            except httpx.RequestError as exc:
                last_exception = exc
                self._logger.warning(
                    "http_runner_transport_error",
                    attempt=attempts,
                    url=url_value,
                    method=method,
                    error=str(exc),
                )
                if attempts >= self._max_retries:
                    break
                delay = self._backoff_delay(attempts)
                if delay > 0:
                    time.sleep(delay)
                continue

            if self._should_retry(method, response.status_code) and attempts < self._max_retries:
                self._logger.info(
                    "http_runner_retry_status",
                    attempt=attempts,
                    url=url_value,
                    method=method,
                    status_code=response.status_code,
                )
                delay = self._backoff_delay(attempts)
                if delay > 0:
                    time.sleep(delay)
                continue

            last_exception = None
            break

        total_duration = time.perf_counter() - overall_start
        duration_ms = int(total_duration * 1000)

        if response is None:
            track_external_http_call(target_label, method, 0, project_id, total_duration)
            error_message = str(last_exception) if last_exception is not None else "HTTP request failed"
            error_metrics = {
                "duration_ms": duration_ms,
                "status": "network_error",
                "response_size": 0,
                "attempts": attempts,
                "retries": max(0, attempts - 1),
            }
            if last_exception is not None:
                error_metrics["error"] = str(last_exception)
            raise HttpRunnerError(
                error_message,
                request_payload=request_payload_record,
                metrics=error_metrics,
                original=last_exception,
            )

        track_external_http_call(target_label, method, response.status_code, project_id, total_duration)

        response_size = len(response.content)
        truncated_body, is_truncated, note = _truncate_text(response.text, self._max_response_size_bytes)
        body_payload: dict[str, Any] = {"text": truncated_body, "truncated": is_truncated}
        if note:
            body_payload["note"] = note

        response_payload: dict[str, Any] = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": body_payload,
        }

        response_json: Any | None
        try:
            response_json = response.json()
        except ValueError:
            response_json = None
        else:
            response_payload["json"] = response_json

        response_payload_record = cast(
            dict[str, Any],
            _sanitize_payload(
                deepcopy(response_payload),
                self._redact_fields,
                self._redaction_placeholder,
                secret_values,
            ),
        )

        metrics = {
            "duration_ms": duration_ms,
            "status": "completed",
            "response_size": response_size,
            "status_code": response.status_code,
            "attempts": attempts,
            "retries": max(0, attempts - 1),
        }

        context_data = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response.text,
            "json": response_json,
        }

        active_context.set_current_response(context_data)

        return HttpRunnerResult(
            request_payload=request_payload_record,
            response_payload=response_payload_record,
            metrics=metrics,
            context_data=context_data,
        )

    def _should_retry(self, method: str, status_code: int) -> bool:
        if status_code not in self._retry_statuses:
            return False
        if not self._retry_methods:
            return True
        return method.upper() in self._retry_methods

    def _backoff_delay(self, attempt: int) -> float:
        delay = self._retry_backoff_factor * (2 ** (attempt - 1))
        return min(delay, _MAX_RETRY_DELAY_SECONDS)


def _normalize_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, (dict, list)):
            normalized[str(key)] = item
        elif item is None:
            normalized[str(key)] = None
        else:
            normalized[str(key)] = str(item)
    return normalized


def _truncate_text(text: str, limit: int) -> tuple[str, bool, str | None]:
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text, False, None
    truncated_bytes = encoded[:limit]
    truncated_text = truncated_bytes.decode("utf-8", errors="replace")
    note = f"Body truncated to {limit} bytes from {len(encoded)} bytes"
    return truncated_text, True, note


def _sanitize_payload(
    data: Any,
    redact_keys: set[str],
    placeholder: str,
    secret_values: set[str],
) -> Any:
    if data is None:
        return None
    if isinstance(data, dict):
        sanitized: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(key, str) and key.lower() in redact_keys:
                sanitized[key] = placeholder
            else:
                sanitized[key] = _sanitize_payload(value, redact_keys, placeholder, secret_values)
        return sanitized
    if isinstance(data, list):
        return [_sanitize_payload(item, redact_keys, placeholder, secret_values) for item in data]
    if isinstance(data, tuple):
        return [_sanitize_payload(item, redact_keys, placeholder, secret_values) for item in data]
    if isinstance(data, set):
        return [_sanitize_payload(item, redact_keys, placeholder, secret_values) for item in data]
    if isinstance(data, (bytes, bytearray)):
        decoded = bytes(data).decode("utf-8", errors="replace")
        return _sanitize_payload(decoded, redact_keys, placeholder, secret_values)
    if isinstance(data, str):
        if _SECRET_TEMPLATE_PATTERN.search(data):
            return placeholder
        masked = data
        for secret in secret_values:
            if secret and secret in masked:
                masked = masked.replace(secret, placeholder)
        return masked
    return data


def _collect_secret_values(context: ExecutionContext) -> set[str]:
    values: set[str] = set()
    secrets = getattr(context, "secrets", {})
    _gather_secret_values(secrets, values)
    return {value for value in values if value}


def _gather_secret_values(value: Any, sink: set[str]) -> None:
    if value is None:
        return
    if isinstance(value, (str, int, float, bool)):
        sink.add(str(value))
        return
    if isinstance(value, (bytes, bytearray)):
        sink.add(bytes(value).decode("utf-8", errors="replace"))
        return
    if isinstance(value, dict):
        for item in value.values():
            _gather_secret_values(item, sink)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _gather_secret_values(item, sink)
        return
    sink.add(str(value))
