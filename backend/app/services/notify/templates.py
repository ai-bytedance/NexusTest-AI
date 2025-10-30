from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class NotificationTemplate:
    """Represents a rendered notification in both text and markdown formats."""

    text: str
    markdown: str
    locale: str = "en"


def _format_pass_rate(value: Any) -> str | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 1:
        numeric *= 100
    return f"{numeric:.1f}%"


def _normalize_status(status: Any) -> str:
    if status is None:
        return "UNKNOWN"
    normalized = str(status).strip()
    if not normalized:
        return "UNKNOWN"
    return normalized.replace("_", " ").upper()


def _entity_label(value: Any) -> str:
    if value is None:
        return "suite"
    label = str(value).strip()
    if not label:
        return "suite"
    return label.replace("_", " ").title()


def render_run_finished_template(payload: dict[str, Any], *, locale: str = "en") -> NotificationTemplate:
    project = payload.get("project_name") or "Unknown Project"
    entity_type = _entity_label(payload.get("entity_type"))
    entity_name = payload.get("entity_name") or payload.get("entity_id") or "N/A"
    status = _normalize_status(payload.get("status"))

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    pass_rate = summary.get("pass_rate", payload.get("pass_rate"))
    pass_rate_label = _format_pass_rate(pass_rate)
    assertions_total = summary.get("assertions_total")
    assertions_passed = summary.get("assertions_passed")

    failure_count: int | None = None
    if isinstance(assertions_total, (int, float)) and isinstance(assertions_passed, (int, float)):
        failure_count = max(int(assertions_total) - int(assertions_passed), 0)

    duration_ms = summary.get("duration_ms") or payload.get("duration_ms")
    finished_at = payload.get("finished_at") or summary.get("finished_at")
    plan_name = payload.get("plan_name")
    report_url = payload.get("report_url")
    summary_text = summary.get("summary") if isinstance(summary.get("summary"), str) else None

    text_lines = [f"[{project}] {entity_type} {entity_name} finished with status {status}"]
    markdown_lines = [f"**{project}** {entity_type} `{entity_name}` finished with status **{status}**"]

    if pass_rate_label:
        text_lines.append(f"Pass rate: {pass_rate_label}")
        markdown_lines.append(f"- Pass rate: **{pass_rate_label}**")
    if isinstance(assertions_total, (int, float)):
        passed = int(assertions_passed or 0)
        total = int(assertions_total)
        text_lines.append(f"Assertions: {passed}/{total}")
        markdown_lines.append(f"- Assertions: **{passed}/{total}**")
    if failure_count is not None and failure_count > 0:
        text_lines.append(f"Failures: {failure_count}")
        markdown_lines.append(f"- Failures: **{failure_count}**")
    if plan_name:
        text_lines.append(f"Execution Plan: {plan_name}")
        markdown_lines.append(f"- Execution Plan: `{plan_name}`")
    if duration_ms:
        text_lines.append(f"Duration: {int(duration_ms)} ms")
        markdown_lines.append(f"- Duration: `{int(duration_ms)} ms`")
    if finished_at:
        text_lines.append(f"Finished at: {finished_at}")
        markdown_lines.append(f"- Finished at: `{finished_at}`")
    if report_url:
        text_lines.append(f"Report: {report_url}")
        markdown_lines.append(f"- [View report]({report_url})")
    if summary_text:
        text_lines.append(summary_text)
        markdown_lines.append("")
        markdown_lines.append(summary_text)

    text = "\n".join(text_lines)
    markdown = "\n".join(markdown_lines)
    return NotificationTemplate(text=text, markdown=markdown, locale=locale)


def render_run_finished_message(payload: dict[str, Any], *, locale: str = "en") -> NotificationTemplate:
    """Backward compatible helper returning the rendered template."""

    return render_run_finished_template(payload, locale=locale)


__all__ = [
    "NotificationTemplate",
    "render_run_finished_message",
    "render_run_finished_template",
]
