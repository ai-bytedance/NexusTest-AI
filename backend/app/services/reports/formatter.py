from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Tuple

from app.core.config import Settings
from app.models.test_report import TestReport
from app.schemas.test_report import TestReportRead


def format_report_summary(report: TestReport, *, settings: Settings) -> dict[str, Any]:
    base = _base_payload(report)
    redact_set = _redact_fields(settings)

    _, request_meta = _prepare_payload(
        base.get("request_payload"),
        max_bytes=settings.max_response_size_bytes,
        redact_keys=redact_set,
        include_payload=False,
    )
    _, response_meta = _prepare_payload(
        base.get("response_payload"),
        max_bytes=settings.max_response_size_bytes,
        redact_keys=redact_set,
        include_payload=False,
    )

    assertions = _redact_data(base.get("assertions_result"), redact_set)
    assertions_total, assertions_passed, pass_rate = _compute_assertion_stats(assertions)

    return {
        "id": base["id"],
        "project_id": base["project_id"],
        "entity_type": base["entity_type"],
        "entity_id": base["entity_id"],
        "status": base["status"],
        "started_at": base["started_at"],
        "finished_at": base.get("finished_at"),
        "duration_ms": base.get("duration_ms"),
        "created_at": base["created_at"],
        "updated_at": base["updated_at"],
        "summary": base.get("summary"),
        "parent_report_id": base.get("parent_report_id"),
        "run_number": base.get("run_number"),
        "retry_attempt": base.get("retry_attempt"),
        "policy_snapshot": base.get("policy_snapshot", {}),
        "failure_signature": base.get("failure_signature"),
        "failure_excerpt": base.get("failure_excerpt"),
        "is_flaky": bool(base.get("is_flaky", False)),
        "flakiness_score": base.get("flakiness_score"),
        "assertions_total": assertions_total,
        "assertions_passed": assertions_passed,
        "pass_rate": pass_rate,
        "response_size": response_meta["size_bytes"],
        "response_payload_truncated": response_meta["truncated"],
        "request_payload_truncated": request_meta["truncated"],
    }


def format_report_detail(report: TestReport, *, settings: Settings) -> dict[str, Any]:
    base = _base_payload(report)
    redact_set = _redact_fields(settings)

    request_payload, request_meta = _prepare_payload(
        base.get("request_payload"),
        max_bytes=settings.max_response_size_bytes,
        redact_keys=redact_set,
        include_payload=True,
    )
    response_payload, response_meta = _prepare_payload(
        base.get("response_payload"),
        max_bytes=settings.max_response_size_bytes,
        redact_keys=redact_set,
        include_payload=True,
    )

    assertions = _redact_data(base.get("assertions_result"), redact_set)
    assertions_total, assertions_passed, pass_rate = _compute_assertion_stats(assertions)

    detail = {
        "id": base["id"],
        "project_id": base["project_id"],
        "entity_type": base["entity_type"],
        "entity_id": base["entity_id"],
        "status": base["status"],
        "started_at": base["started_at"],
        "finished_at": base.get("finished_at"),
        "duration_ms": base.get("duration_ms"),
        "created_at": base["created_at"],
        "updated_at": base["updated_at"],
        "summary": base.get("summary"),
        "parent_report_id": base.get("parent_report_id"),
        "run_number": base.get("run_number"),
        "retry_attempt": base.get("retry_attempt"),
        "policy_snapshot": base.get("policy_snapshot", {}),
        "failure_signature": base.get("failure_signature"),
        "failure_excerpt": base.get("failure_excerpt"),
        "is_flaky": bool(base.get("is_flaky", False)),
        "flakiness_score": base.get("flakiness_score"),
        "request_payload": request_payload,
        "response_payload": response_payload,
        "assertions_result": assertions,
        "metrics": _redact_data(base.get("metrics"), redact_set),
        "assertions_total": assertions_total,
        "assertions_passed": assertions_passed,
        "pass_rate": pass_rate,
        "response_size": response_meta["size_bytes"],
        "response_payload_truncated": response_meta["truncated"],
        "request_payload_truncated": request_meta["truncated"],
        "redacted_fields": sorted(redact_set),
    }

    if request_meta["note"]:
        detail["request_payload_note"] = request_meta["note"]
    if response_meta["note"]:
        detail["response_payload_note"] = response_meta["note"]

    return detail


def _base_payload(report: TestReport) -> dict[str, Any]:
    payload = TestReportRead.model_validate(report)
    return payload.model_dump(mode="json")


def _redact_fields(settings: Settings) -> set[str]:
    return {item.lower() for item in (settings.redact_fields or [])}


def _prepare_payload(
    payload: Any,
    *,
    max_bytes: int,
    redact_keys: set[str],
    include_payload: bool,
) -> Tuple[Any | None, dict[str, Any]]:
    redacted = _redact_data(deepcopy(payload), redact_keys)
    size_bytes = _measure_size(redacted)
    truncated = size_bytes > max_bytes if max_bytes is not None else False
    note: str | None = None

    formatted_payload: Any | None
    if include_payload:
        if truncated:
            note = (
                "Payload truncated because it exceeded the configured limit of "
                f"{max_bytes} bytes (actual size: {size_bytes} bytes)."
            )
            formatted_payload = {"_truncated": True, "_note": note}
        else:
            formatted_payload = redacted
    else:
        formatted_payload = None
        if truncated:
            note = (
                "Payload exceeds the configured limit of "
                f"{max_bytes} bytes (actual size: {size_bytes} bytes)."
            )

    metadata = {"size_bytes": size_bytes, "truncated": truncated, "note": note}
    return formatted_payload, metadata


def _redact_data(data: Any, redact_keys: set[str]) -> Any:
    if data is None:
        return None
    if isinstance(data, dict):
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(key, str) and key.lower() in redact_keys:
                result[key] = "***"
            else:
                result[key] = _redact_data(value, redact_keys)
        return result
    if isinstance(data, list):
        return [_redact_data(item, redact_keys) for item in data]
    if isinstance(data, tuple):  # pragma: no cover - defensive
        return [_redact_data(item, redact_keys) for item in data]
    return data


def _measure_size(value: Any) -> int:
    if value is None:
        return 0
    try:
        serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except TypeError:  # pragma: no cover - guardrail
        serialized = json.dumps(_stringify(value), ensure_ascii=False, separators=(",", ":"))
    return len(serialized.encode("utf-8"))


def _stringify(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _stringify(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_stringify(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _compute_assertion_stats(assertions: Any) -> Tuple[int, int, float]:
    total = 0
    passed = 0
    if isinstance(assertions, dict):
        results = assertions.get("results")
        if isinstance(results, list):
            total = len(results)
            passed = sum(1 for item in results if isinstance(item, dict) and item.get("passed") is True)
    pass_rate = round(passed / total, 4) if total else 0.0
    return total, passed, pass_rate


__all__ = ["format_report_summary", "format_report_detail"]
