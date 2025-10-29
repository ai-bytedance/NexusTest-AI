from __future__ import annotations

import difflib
import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from jinja2 import Environment, PackageLoader, select_autoescape

from app.core.config import Settings
from app.services.exports.report_templates import ReportTemplateDefinition, get_template_definition

MAX_DIFF_CHARACTERS = 8000


@lru_cache(maxsize=1)
def _markdown_env() -> Environment:
    env = Environment(
        loader=PackageLoader("app.services.exports", "templates/markdown"),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["to_pretty_json"] = _format_json
    return env


@lru_cache(maxsize=1)
def _html_env() -> Environment:
    env = Environment(
        loader=PackageLoader("app.services.exports", "templates/pdf"),
        autoescape=select_autoescape(("html", "xml")),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["to_pretty_json"] = _format_json
    return env


def render_markdown_report(report: dict[str, Any], template_key: str, settings: Settings) -> str:
    definition = _get_template_or_raise(template_key)
    context = _build_context(report, definition, settings)
    template = _markdown_env().get_template(definition.markdown_template)
    return template.render(context)


def render_pdf_report(report: dict[str, Any], template_key: str, settings: Settings) -> bytes:
    definition = _get_template_or_raise(template_key)
    context = _build_context(report, definition, settings)
    template = _html_env().get_template(definition.pdf_template)
    html_content = template.render(context)

    if settings.pdf_engine == "wkhtml":
        raise RuntimeError("wkhtml-based PDF generation is not configured in this deployment")

    try:
        from weasyprint import HTML  # type: ignore import-not-found
        from weasyprint.fonts import FontConfiguration  # type: ignore import-not-found
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("WeasyPrint is required for PDF export but is not installed") from exc

    font_config = FontConfiguration()
    document = HTML(string=html_content, base_url=str(Path.cwd()))
    return document.write_pdf(font_config=font_config)


def _get_template_or_raise(key: str) -> ReportTemplateDefinition:
    definition = get_template_definition(key)
    if definition is None:
        raise ValueError(f"Unknown report export template: {key}")
    return definition


def _build_context(report: dict[str, Any], template: ReportTemplateDefinition, settings: Settings) -> dict[str, Any]:
    assertions = _build_assertions(report)
    failures = assertions["failures"]
    payload_context = {
        "requests": _build_payload_entries(report, "request"),
        "responses": _build_payload_entries(report, "response"),
    }

    context = {
        "template": template,
        "branding": _build_branding(settings),
        "metadata": _build_metadata(report),
        "summary_text": (report.get("summary") or "").strip() or None,
        "assertions": assertions,
        "failures": failures,
        "steps": _build_steps(report),
        "payloads": payload_context,
        "metrics": _build_metrics(report),
        "environment": _build_environment(report),
        "dataset": _build_dataset(report),
        "redaction": _build_redaction(report),
        "report": report,
        "assets": {
            "font_uri": _resolve_font_uri(settings.report_export_font_path),
        },
    }
    return context


def _build_metadata(report: dict[str, Any]) -> dict[str, Any]:
    started_at = _format_datetime(report.get("started_at"))
    finished_at = _format_datetime(report.get("finished_at"))
    created_at = _format_datetime(report.get("created_at"))
    updated_at = _format_datetime(report.get("updated_at"))
    duration_display = _format_duration(report.get("duration_ms"))
    pass_rate_display = _format_percent(report.get("pass_rate"))
    assertions_total = report.get("assertions_total") or 0
    assertions_passed = report.get("assertions_passed") or 0
    response_size_display = _format_bytes(report.get("response_size"))

    return {
        "id": str(report.get("id")),
        "project_id": str(report.get("project_id")),
        "entity_type": report.get("entity_type"),
        "entity_id": str(report.get("entity_id")),
        "status": report.get("status"),
        "started_at": started_at,
        "finished_at": finished_at,
        "created_at": created_at,
        "updated_at": updated_at,
        "duration_display": duration_display,
        "assertions_display": f"{assertions_passed}/{assertions_total}",
        "pass_rate_display": pass_rate_display,
        "response_size_display": response_size_display,
    }


def _build_branding(settings: Settings) -> dict[str, Any | None]:
    return {
        "logo": settings.report_export_branding_logo,
        "title": settings.report_export_branding_title,
        "footer": settings.report_export_branding_footer,
        "company": settings.report_export_branding_company,
    }


def _build_payload_entries(report: dict[str, Any], payload_type: str) -> list[dict[str, Any | None]]:
    field_name = f"{payload_type}_payload"
    payload = report.get(field_name)
    truncated = bool(report.get(f"{payload_type}_payload_truncated"))
    note = report.get(f"{payload_type}_payload_note")

    entries: list[dict[str, Any | None]] = []
    if isinstance(payload, dict) and isinstance(payload.get("steps"), list):
        steps: Iterable[Any] = payload.get("steps", [])
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue
            alias = step.get("alias") or f"Step {index}"
            case_id = step.get("case_id")
            body = step.get(payload_type)
            entries.append(
                {
                    "index": index,
                    "alias": alias,
                    "case_id": str(case_id) if case_id else None,
                    "truncated": truncated,
                    "note": note,
                    "content": _format_json(body) if body is not None else None,
                    "summary": _summarise_payload(body),
                }
            )
    else:
        entries.append(
            {
                "index": 1,
                "alias": None,
                "case_id": None,
                "truncated": truncated,
                "note": note,
                "content": _format_json(payload) if payload is not None else None,
                "summary": _summarise_payload(payload),
            }
        )
    return entries


def _build_assertions(report: dict[str, Any]) -> dict[str, Any]:
    raw = report.get("assertions_result") or {}
    total = int(report.get("assertions_total") or 0)
    passed = int(report.get("assertions_passed") or 0)
    failed = max(total - passed, 0)

    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    if isinstance(raw, dict):
        if isinstance(raw.get("results"), list):
            for item in raw["results"]:
                entry = _convert_assertion(item, step_alias=None, case_id=None)
                if entry is not None:
                    results.append(entry)
                    if not entry["passed"]:
                        failures.append(entry)
        elif isinstance(raw.get("steps"), list):
            for step in raw["steps"]:
                if not isinstance(step, dict):
                    continue
                alias = step.get("alias")
                case_id = step.get("case_id")
                if isinstance(step.get("assertions"), list):
                    for assertion in step["assertions"]:
                        entry = _convert_assertion(assertion, step_alias=alias, case_id=case_id)
                        if entry is not None:
                            results.append(entry)
                            if not entry["passed"]:
                                failures.append(entry)
                if step.get("error"):
                    failures.append(
                        {
                            "name": alias or "Step Error",
                            "operator": "error",
                            "passed": False,
                            "message": step.get("error"),
                            "expected_display": None,
                            "actual_display": None,
                            "diff": None,
                            "step": alias,
                            "case_id": str(case_id) if case_id else None,
                            "path": None,
                        }
                    )
        elif raw.get("error"):
            failures.append(
                {
                    "name": "Report Error",
                    "operator": "error",
                    "passed": False,
                    "message": raw.get("error"),
                    "expected_display": None,
                    "actual_display": None,
                    "diff": None,
                    "step": None,
                    "case_id": None,
                    "path": None,
                }
            )

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate_display": _format_percent(report.get("pass_rate")),
        "results": results,
        "failures": failures,
        "error": raw.get("error") if isinstance(raw, dict) else None,
    }


def _convert_assertion(assertion: Any, *, step_alias: str | None, case_id: Any) -> dict[str, Any] | None:
    if not isinstance(assertion, dict):
        return None
    passed = bool(assertion.get("passed"))
    name = assertion.get("name") or assertion.get("operator") or "assertion"
    operator = assertion.get("operator")
    message = assertion.get("message")
    expected = assertion.get("expected")
    actual = assertion.get("actual")
    diff = None if passed else _generate_diff(expected, actual)

    entry = {
        "name": str(name) if name is not None else "assertion",
        "operator": operator,
        "passed": passed,
        "message": message,
        "expected": expected,
        "actual": actual,
        "expected_display": _describe_value(expected),
        "actual_display": _describe_value(actual),
        "diff": diff,
        "step": step_alias,
        "case_id": str(case_id) if case_id else None,
        "path": assertion.get("path"),
    }
    return entry


def _generate_diff(expected: Any, actual: Any) -> str | None:
    expected_lines = _split_lines_for_diff(expected)
    actual_lines = _split_lines_for_diff(actual)
    diff_lines = list(
        difflib.unified_diff(
            expected_lines,
            actual_lines,
            fromfile="expected",
            tofile="actual",
            lineterm="",
        )
    )
    if not diff_lines:
        return None
    diff_text = "\n".join(diff_lines)
    if len(diff_text) > MAX_DIFF_CHARACTERS:
        return diff_text[:MAX_DIFF_CHARACTERS] + "\n… diff truncated"
    return diff_text


def _split_lines_for_diff(value: Any) -> list[str]:
    if value is None:
        return ["null"]
    if isinstance(value, (dict, list)):
        return _format_json(value).splitlines()
    if isinstance(value, (int, float, bool)):
        return [json.dumps(value)]
    text = str(value)
    if not text:
        return [" "]
    return text.splitlines()


def _build_steps(report: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = report.get("metrics") or {}
    metric_steps = []
    if isinstance(metrics.get("steps"), list):
        metric_steps = [step for step in metrics["steps"] if isinstance(step, dict)]

    assertions = report.get("assertions_result") or {}
    steps: list[dict[str, Any]] = []

    if isinstance(assertions, dict) and isinstance(assertions.get("steps"), list):
        for index, step in enumerate(assertions["steps"], start=1):
            if not isinstance(step, dict):
                continue
            alias = step.get("alias") or f"Step {index}"
            case_id = step.get("case_id")
            metrics_payload = _match_step_metrics(metric_steps, alias, case_id)
            status = "passed" if step.get("passed") else "failed"
            if step.get("error"):
                status = "error"
            steps.append(
                {
                    "index": index,
                    "alias": alias,
                    "case_id": str(case_id) if case_id else None,
                    "status": status,
                    "assertion_count": len(step.get("assertions") or []),
                    "error": step.get("error"),
                    "metrics": metrics_payload,
                }
            )
    else:
        status = report.get("status")
        steps.append(
            {
                "index": 1,
                "alias": "Execution",
                "case_id": str(report.get("entity_id")),
                "status": status,
                "assertion_count": len((assertions.get("results") or []) if isinstance(assertions, dict) else []),
                "error": assertions.get("error") if isinstance(assertions, dict) else None,
                "metrics": {
                    "duration_display": _format_duration(report.get("duration_ms")),
                    "response_size_display": _format_bytes(report.get("response_size")),
                    "status": status,
                },
            }
        )
    return steps


def _match_step_metrics(metric_steps: list[dict[str, Any]], alias: Any, case_id: Any) -> dict[str, Any | None]:
    target_alias = str(alias) if alias is not None else None
    target_case = str(case_id) if case_id else None
    for step in metric_steps:
        candidate_alias = step.get("alias")
        candidate_case = step.get("case_id")
        alias_matches = target_alias is not None and candidate_alias == target_alias
        case_matches = target_case is not None and candidate_case and str(candidate_case) == target_case
        if alias_matches or case_matches:
            return {
                "duration_display": _format_duration(step.get("duration_ms")),
                "response_size_display": _format_bytes(step.get("response_size")),
                "status": step.get("status"),
            }
    return {
        "duration_display": None,
        "response_size_display": None,
        "status": None,
    }


def _build_metrics(report: dict[str, Any]) -> dict[str, Any]:
    metrics = report.get("metrics") or {}
    steps_info = []
    if isinstance(metrics.get("steps"), list):
        for index, step in enumerate(metrics["steps"], start=1):
            if not isinstance(step, dict):
                continue
            steps_info.append(
                {
                    "index": index,
                    "alias": step.get("alias") or f"Step {index}",
                    "case_id": str(step.get("case_id")) if step.get("case_id") else None,
                    "duration_display": _format_duration(step.get("duration_ms")),
                    "response_size_display": _format_bytes(step.get("response_size")),
                    "status": step.get("status"),
                }
            )
    return {
        "duration_display": _format_duration(report.get("duration_ms")),
        "response_size_display": _format_bytes(report.get("response_size")),
        "status": report.get("status"),
        "task_id": metrics.get("task_id"),
        "raw": metrics,
        "steps": steps_info,
    }


def _build_environment(report: dict[str, Any]) -> dict[str, Any] | None:
    metrics = report.get("metrics") or {}
    environment = metrics.get("environment") or report.get("environment")
    if isinstance(environment, dict):
        return environment

    details: dict[str, Any] = {}
    for key in ("environment_id", "environment_name", "environment_region", "environment_url"):
        value = metrics.get(key) or report.get(key)
        if value:
            details[key] = value
    return details or None


def _build_dataset(report: dict[str, Any]) -> dict[str, Any] | None:
    metrics = report.get("metrics") or {}
    dataset = metrics.get("dataset") or report.get("dataset")
    if isinstance(dataset, dict):
        return dataset

    details: dict[str, Any] = {}
    for key in ("dataset_id", "dataset_name", "dataset_version"):
        value = metrics.get(key) or report.get(key)
        if value:
            details[key] = value
    return details or None


def _build_redaction(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_truncated": bool(report.get("request_payload_truncated")),
        "response_truncated": bool(report.get("response_payload_truncated")),
        "request_note": report.get("request_payload_note"),
        "response_note": report.get("response_payload_note"),
        "redacted_fields": sorted(report.get("redacted_fields") or []),
    }


def _describe_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return _format_json(value)
    return str(value)


def _summarise_payload(payload: Any) -> str:
    if payload is None:
        return "No data captured"
    if isinstance(payload, dict):
        keys = list(payload.keys())
        if not keys:
            return "Empty object"
        preview = ", ".join(keys[:5])
        if len(keys) > 5:
            preview += " …"
        return f"Object keys: {preview}"
    if isinstance(payload, list):
        length = len(payload)
        return f"List with {length} item{'s' if length != 1 else ''}"
    text = str(payload)
    return text if len(text) <= 80 else text[:77] + "…"


def _resolve_font_uri(font_path: str | None) -> str | None:
    if not font_path:
        return None
    candidate = Path(font_path).expanduser()
    if candidate.exists():
        try:
            return candidate.resolve().as_uri()
        except ValueError:  # pragma: no cover - fallback for unsupported OS schemes
            return f"file://{candidate.resolve()}"
    return None


def _format_datetime(value: Any) -> str:
    if value in (None, ""):
        return "N/A"
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value)
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.strftime("%Y-%m-%d %H:%M:%S %Z")


def _format_duration(value: Any) -> str:
    if value in (None, ""):
        return "N/A"
    try:
        ms = float(value)
    except (TypeError, ValueError):
        return str(value)
    if ms < 1000:
        return f"{int(ms)} ms"
    seconds = ms / 1000.0
    if seconds < 60:
        return f"{seconds:.2f} s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {seconds:.1f}s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(minutes)}m"


def _format_percent(value: Any) -> str:
    try:
        numeric = float(value) * 100.0
    except (TypeError, ValueError):
        return "0.0%"
    return f"{numeric:.1f}%"


def _format_bytes(value: Any) -> str:
    if value in (None, ""):
        return "N/A"
    try:
        size = float(value)
    except (TypeError, ValueError):
        return str(value)
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024.0
        index += 1
    return f"{size:.2f} {units[index]}"


def _format_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default)
    except TypeError:
        return json.dumps(_json_default(value), ensure_ascii=False, indent=2, sort_keys=True)


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return str(value)


__all__ = [
    "render_markdown_report",
    "render_pdf_report",
]
