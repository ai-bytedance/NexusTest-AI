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

    def execute(
        self,
        inputs: dict[str, Any],
        context: ExecutionContext | None = None,
        *,
        prepared_inputs: dict[str, Any] | None = None,
        display_inputs: dict[str, Any] | None = None,
    ) -> HttpRunnerResult:
        active_context = context or ExecutionContext()
        actual_inputs = prepared_inputs if prepared_inputs is not None else render_value(inputs, active_context)
        display_mapping = display_inputs if isinstance(display_inputs, dict) else (
            actual_inputs if isinstance(actual_inputs, dict) else {}
        )

        if not isinstance(actual_inputs, dict):
            raise ValueError("HTTP runner requires input payload to be an object")

        method = str(actual_inputs.get("method", "GET")).upper()
        url_value = actual_inputs.get("url")
        if not isinstance(url_value, str) or not url_value:
            raise ValueError("HTTP runner requires a non-empty URL")

        display_url = display_mapping.get("url") if isinstance(display_mapping, dict) else None
        request_url = display_url if isinstance(display_url, str) and display_url else url_value

        headers = _normalize_mapping(actual_inputs.get("headers"))
        display_headers = _normalize_mapping(display_mapping.get("headers"))
        params = _normalize_mapping(actual_inputs.get("params"))
        display_params = _normalize_mapping(display_mapping.get("params"))

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

        request_kwargs: dict[str, Any] = {
            "headers": headers or None,
            "params": params or None,
        }

        if "json" in actual_inputs:
            actual_json = actual_inputs.get("json")
            request_kwargs["json"] = actual_json
            display_json = display_mapping.get("json") if isinstance(display_mapping, dict) else None
            if display_json is not None:
                request_payload["json"] = display_json
            else:
                request_payload["json"] = actual_json
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

        timeout = httpx.Timeout(self._timeout_seconds)
        start = time.perf_counter()
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.request(method, url_value, **{k: v for k, v in request_kwargs.items() if v is not None})
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
