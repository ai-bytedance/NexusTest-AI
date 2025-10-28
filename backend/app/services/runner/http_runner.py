from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.services.execution.context import ExecutionContext, render_value


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
    def __init__(self, timeout_seconds: float, max_response_size_bytes: int) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_response_size_bytes = max_response_size_bytes

    def execute(self, inputs: dict[str, Any], context: ExecutionContext | None = None) -> HttpRunnerResult:
        active_context = context or ExecutionContext()
        prepared_inputs = render_value(inputs, active_context)

        method = str(prepared_inputs.get("method", "GET")).upper()
        url = prepared_inputs.get("url")
        if not isinstance(url, str) or not url:
            raise ValueError("HTTP runner requires a non-empty URL")

        headers = _normalize_mapping(prepared_inputs.get("headers"))
        params = _normalize_mapping(prepared_inputs.get("params"))

        request_payload: dict[str, Any] = {
            "method": method,
            "url": url,
        }
        if headers:
            request_payload["headers"] = headers
        if params:
            request_payload["params"] = params

        request_kwargs: dict[str, Any] = {
            "headers": headers or None,
            "params": params or None,
        }

        if "json" in prepared_inputs:
            request_kwargs["json"] = prepared_inputs["json"]
            request_payload["json"] = prepared_inputs["json"]
        elif "body" in prepared_inputs:
            body = prepared_inputs.get("body")
            if isinstance(body, (dict, list)):
                request_kwargs["json"] = body
                request_payload["json"] = body
            elif body is not None:
                if isinstance(body, (bytes, bytearray)):
                    content_bytes = bytes(body)
                    display_body = content_bytes.decode("utf-8", errors="replace")
                else:
                    display_body = str(body)
                    content_bytes = display_body.encode("utf-8")
                request_kwargs["content"] = content_bytes
                truncated_body, is_truncated, note = _truncate_text(display_body, self._max_response_size_bytes)
                body_payload = {"text": truncated_body, "truncated": is_truncated}
                if note:
                    body_payload["note"] = note
                request_payload["body"] = body_payload

        timeout = httpx.Timeout(self._timeout_seconds)
        start = time.perf_counter()
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.request(method, url, **{k: v for k, v in request_kwargs.items() if v is not None})
        except httpx.RequestError as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            metrics = {
                "duration_ms": duration_ms,
                "status": "network_error",
                "response_size": 0,
                "error": str(exc),
            }
            raise HttpRunnerError(
                str(exc),
                request_payload=request_payload,
                metrics=metrics,
                original=exc,
            ) from exc

        duration_ms = int((time.perf_counter() - start) * 1000)
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

        metrics = {
            "duration_ms": duration_ms,
            "status": "completed",
            "response_size": response_size,
        }

        context_data = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response.text,
            "json": response_json,
        }

        active_context.set_current_response(context_data)

        return HttpRunnerResult(
            request_payload=request_payload,
            response_payload=response_payload,
            metrics=metrics,
            context_data=context_data,
        )


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
