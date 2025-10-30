from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from app.models.test_report import ReportStatus, TestReport

_MAX_EXCERPT_LENGTH = 512
_MAX_VALUE_LENGTH = 200
_NUMBER_PATTERN = re.compile(r"\b\d{4,}\b")
_HEX_PATTERN = re.compile(r"\b[0-9a-f]{8,}\b", re.IGNORECASE)


@dataclass(frozen=True)
class FailureSignature:
    hash: str
    title: str
    pattern: str | None
    excerpt: str
    components: dict[str, Any]


def build_failure_signature(report: TestReport) -> FailureSignature | None:
    if report.status not in {ReportStatus.FAILED, ReportStatus.ERROR}:
        return None

    status_code = _extract_status_code(report)
    assertion = _first_failing_assertion(report.assertions_result or {})

    if assertion:
        operator = _normalize_text(assertion.get("operator"), 64) or "unknown"
        path = _normalize_text(assertion.get("path") or assertion.get("name"), 96) or "root"
        expected = _normalize_value(assertion.get("expected"))
        actual = _normalize_value(assertion.get("actual"))
        message = _normalize_text(assertion.get("message"), 160)
        components: dict[str, Any] = {
            "mode": "assertion",
            "operator": operator,
            "path": path,
            "expected": expected,
            "actual": actual,
            "status_code": status_code,
        }
        if message:
            components["message"] = message
        excerpt = _build_assertion_excerpt(operator, path, expected, actual, message)
        title = _build_assertion_title(operator, path)
        pattern = _build_assertion_pattern(operator, path, expected)
    else:
        error_message = _normalize_text(_extract_error_message(report), 200)
        snippet = _normalize_text(_extract_body_snippet(report.response_payload), 200)
        components = {
            "mode": "response",
            "status_code": status_code,
            "error": error_message or "unknown",
            "snippet": snippet or "none",
        }
        excerpt = _build_response_excerpt(error_message, snippet, status_code)
        title = _build_response_title(error_message, status_code)
        pattern = snippet or error_message or None

    fingerprint = _stable_dump(components)
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()

    excerpt = _truncate(excerpt, _MAX_EXCERPT_LENGTH)
    title = _truncate(title or excerpt, 160)
    pattern = _truncate(pattern, 512) if pattern else None

    return FailureSignature(
        hash=digest,
        title=title or "Failure",
        pattern=pattern,
        excerpt=excerpt,
        components=components,
    )


def _first_failing_assertion(payload: dict[str, Any]) -> dict[str, Any] | None:
    results = payload.get("results")
    if not isinstance(results, list):
        return None
    for item in results:
        if isinstance(item, dict) and item.get("passed") is False:
            return item
    return None


def _extract_status_code(report: TestReport) -> int | None:
    payload = report.response_payload or {}
    if isinstance(payload, dict):
        status_value = payload.get("status_code") or payload.get("status")
        if isinstance(status_value, int):
            return status_value
        try:
            return int(status_value)
        except (TypeError, ValueError):
            pass
    metrics = report.metrics or {}
    status_value = metrics.get("status_code")
    if isinstance(status_value, int):
        return status_value
    try:
        return int(status_value)
    except (TypeError, ValueError):
        return None


def _extract_error_message(report: TestReport) -> str:
    metrics = report.metrics or {}
    for key in ("error", "message", "reason", "detail"):
        value = metrics.get(key)
        if isinstance(value, str) and value.strip():
            return value
    summary = report.summary
    if isinstance(summary, str) and summary.strip():
        return summary
    assertions = report.assertions_result or {}
    if isinstance(assertions, dict):
        note = assertions.get("message")
        if isinstance(note, str) and note.strip():
            return note
    return ""


def _extract_body_snippet(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    json_body = payload.get("json")
    if json_body is not None:
        return _normalize_value(json_body)
    body = payload.get("body")
    if isinstance(body, dict):
        candidate = body.get("text") or body.get("value")
        return candidate if isinstance(candidate, str) else ""
    if isinstance(body, str):
        return body
    return ""


def _build_assertion_title(operator: str, path: str) -> str:
    base = operator.replace("_", " ").title() if operator else "Assertion"
    if path and path != "root":
        return f"{base} at {path}"
    return base


def _build_assertion_excerpt(operator: str, path: str, expected: str, actual: str, message: str | None) -> str:
    segments: list[str] = []
    subject = operator or "assertion"
    if path and path != "root":
        subject = f"{subject} at {path}"
    segments.append(subject)
    if expected:
        segments.append(f"expected {expected}")
    if actual:
        segments.append(f"got {actual}")
    if message:
        segments.append(message)
    return " — ".join(segment for segment in segments if segment)


def _build_assertion_pattern(operator: str, path: str, expected: str) -> str:
    parts = [operator or "assertion"]
    if path and path != "root":
        parts.append(path)
    if expected:
        parts.append(expected)
    return " :: ".join(parts)


def _build_response_title(error_message: str, status_code: int | None) -> str:
    status_text = f"{status_code}" if status_code is not None else "Unknown"
    if error_message:
        return f"{status_text} response anomaly"
    return f"{status_text} response anomaly"


def _build_response_excerpt(error_message: str, snippet: str, status_code: int | None) -> str:
    parts: list[str] = []
    if status_code is not None:
        parts.append(f"status {status_code}")
    if error_message:
        parts.append(error_message)
    if snippet:
        parts.append(snippet)
    return " — ".join(parts)


def _normalize_text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    text = str(value)
    text = " ".join(text.split())
    text = _redact_dynamic_tokens(text)
    return _truncate(text, limit)


def _normalize_value(value: Any, limit: int = _MAX_VALUE_LENGTH) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _truncate(str(value), limit)
    if isinstance(value, (dict, list, tuple, set)):
        try:
            sanitized = _sanitize_structure(value)
            text = json.dumps(sanitized, sort_keys=True, separators=(",", ":"))
        except TypeError:
            text = str(value)
    else:
        text = str(value)
    text = _redact_dynamic_tokens(text)
    return _truncate(text, limit)


def _sanitize_structure(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize_structure(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_structure(item) for item in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value
    return _redact_dynamic_tokens(str(value))


def _redact_dynamic_tokens(text: str) -> str:
    redacted = _NUMBER_PATTERN.sub("<num>", text)
    redacted = _HEX_PATTERN.sub("<hex>", redacted)
    return redacted


def _truncate(value: str, limit: int) -> str:
    if not value:
        return ""
    if limit <= 0 or len(value) <= limit:
        return value
    return value[: max(1, limit - 1)].rstrip() + "…"


def _stable_dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
