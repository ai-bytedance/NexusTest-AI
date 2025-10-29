from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from typing import Any, Iterable, Sequence
from urllib.parse import urlparse

from app.models.api import Api
from app.models.test_case import TestCase
from app.schemas.ai_chat import GeneratedCase

_DEFAULT_TITLE = "AI Assistant Chat"


def generate_chat_title(text: str, *, max_length: int = 80) -> str:
    candidate = unicodedata.normalize("NFKC", text or "").strip()
    if not candidate:
        return _DEFAULT_TITLE
    candidate = re.sub(r"\s+", " ", candidate)
    if len(candidate) <= max_length:
        return candidate
    truncated = candidate[: max_length - 1].rstrip()
    return f"{truncated}…"


def normalize_cases(raw_cases: Sequence[dict[str, Any]] | None, api: Api | None) -> list[GeneratedCase]:
    if not raw_cases:
        return []
    normalized: list[GeneratedCase] = []
    for index, raw in enumerate(raw_cases):
        if not isinstance(raw, dict):
            continue
        name = _resolve_name(raw, index)
        description = _safe_str(raw.get("description"))
        request = _resolve_request(raw, api)
        assertions = _resolve_assertions(raw)
        expected = _resolve_expected(raw, assertions)
        metadata = {}
        additional_notes = raw.get("notes") or raw.get("metadata")
        if isinstance(additional_notes, dict):
            metadata = additional_notes
        elif isinstance(additional_notes, list):
            metadata = {"notes": additional_notes}
        generated = GeneratedCase(
            name=name,
            description=description,
            request=request,
            expected=expected,
            assertions=assertions,
            metadata=metadata or None,
        )
        normalized.append(generated)
    return normalized


def build_test_case_models(
    cases: Iterable[GeneratedCase],
    *,
    project_id: Any,
    api_id: Any,
    created_by: Any,
) -> list[TestCase]:
    models: list[TestCase] = []
    for item in cases:
        inputs = _prepare_inputs(item.request)
        expected = deepcopy(item.expected or {})
        assertions = deepcopy(item.assertions or [])
        name = item.name.strip() if item.name else "Generated Case"
        if len(name) > 255:
            name = f"{name[:252]}…"
        model = TestCase(
            project_id=project_id,
            api_id=api_id,
            name=name,
            inputs=inputs,
            expected=expected,
            assertions=assertions,
            param_mapping={},
            enabled=True,
            created_by=created_by,
        )
        models.append(model)
    return models


def _resolve_name(raw: dict[str, Any], index: int) -> str:
    name = raw.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    summary = raw.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    return f"Generated Case {index + 1}"


def _resolve_request(raw: dict[str, Any], api: Api | None) -> dict[str, Any]:
    request = {}
    candidate = raw.get("request")
    if not isinstance(candidate, dict):
        candidate = raw.get("inputs") if isinstance(raw.get("inputs"), dict) else None
    if candidate is None:
        candidate = _resolve_request_from_steps(raw.get("steps"))
    base_method = (api.method if api else "GET") if api else "GET"
    method_value = _safe_method(candidate.get("method") if isinstance(candidate, dict) else None, default=base_method)
    request["method"] = method_value

    url_value = None
    if isinstance(candidate, dict):
        url_value = candidate.get("url") or candidate.get("path")
    if not isinstance(url_value, str) or not url_value:
        url_value = raw.get("path") if isinstance(raw.get("path"), str) else None
    if isinstance(url_value, str) and url_value.startswith("http"):
        parsed = urlparse(url_value)
        url_value = parsed.path or "/"
    if not isinstance(url_value, str) or not url_value:
        url_value = api.path if api and isinstance(api.path, str) else "/"
    request["url"] = url_value

    if isinstance(candidate, dict):
        for key in ("headers", "params", "json", "body", "data"):
            value = candidate.get(key)
            if value is not None:
                request[key] = value
    body_value = request.get("body")
    if isinstance(body_value, dict) and "json" not in request:
        request["json"] = body_value
    if "body" in request and not isinstance(request["body"], (str, bytes)):
        request.pop("body")
    if "data" in request and request.get("data") is None:
        request.pop("data")
    return request


def _resolve_request_from_steps(steps: Any) -> dict[str, Any] | None:
    if not isinstance(steps, Sequence):
        return None
    for step in steps:
        if not isinstance(step, dict):
            continue
        action = step.get("action")
        if isinstance(action, str) and action.lower() in {"send_request", "request"}:
            payload = {key: value for key, value in step.items() if key != "action"}
            method = step.get("method")
            if method:
                payload["method"] = method
            path = step.get("path")
            if path:
                payload["path"] = path
            return payload
    return None


def _resolve_assertions(raw: dict[str, Any]) -> list[dict[str, Any]]:
    assertions = raw.get("assertions")
    if isinstance(assertions, list):
        return [item for item in assertions if isinstance(item, dict)]
    if isinstance(assertions, dict):
        items = assertions.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    expected = raw.get("expected")
    if isinstance(expected, dict):
        status = expected.get("status_code")
        if isinstance(status, int):
            return [{"operator": "status_code", "expected": status}]
    status_hint = raw.get("expected_status")
    if isinstance(status_hint, int):
        return [{"operator": "status_code", "expected": status_hint}]
    return []


def _resolve_expected(raw: dict[str, Any], assertions: Sequence[dict[str, Any]]) -> dict[str, Any]:
    expected_payload: dict[str, Any] = {}
    status = _extract_status(assertions)
    if status is None:
        status_hint = raw.get("expected_status")
        if isinstance(status_hint, int):
            status = status_hint
    if status is None:
        status = 200
    expected_payload["status_code"] = status

    body = raw.get("expected")
    if isinstance(body, dict) and body:
        expected_payload["body"] = body
    elif isinstance(raw.get("response"), dict):
        expected_payload["body"] = raw["response"]
    elif isinstance(raw.get("example"), dict):
        expected_payload["body"] = raw["example"]
    return expected_payload


def _extract_status(assertions: Sequence[dict[str, Any]]) -> int | None:
    for definition in assertions:
        operator = str(definition.get("operator", "")).lower()
        if operator == "status_code":
            expected = definition.get("expected")
            if isinstance(expected, int):
                return expected
    return None


def _prepare_inputs(request: dict[str, Any] | None) -> dict[str, Any]:
    payload = deepcopy(request or {})
    method = payload.get("method")
    payload["method"] = _safe_method(method)
    url_value = payload.get("url")
    if not isinstance(url_value, str) or not url_value:
        payload["url"] = "/"
    if isinstance(payload.get("url"), str):
        payload["url"] = payload["url"].strip() or "/"
    return payload


def _safe_method(value: Any, *, default: str = "GET") -> str:
    if isinstance(value, str) and value.strip():
        return value.strip().upper()
    return default.upper()


def _safe_str(value: Any) -> str | None:
    if isinstance(value, str):
        candidate = value.strip()
        return candidate or None
    return None


__all__ = [
    "build_test_case_models",
    "generate_chat_title",
    "normalize_cases",
]
