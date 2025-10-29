from __future__ import annotations

from typing import Any


def render_run_finished_message(payload: dict[str, Any]) -> str:
    project = payload.get("project_name", "Unknown Project")
    entity_type = str(payload.get("entity_type", "suite")).capitalize()
    entity_name = payload.get("entity_name") or payload.get("entity_id")
    status = str(payload.get("status", "unknown")).upper()
    pass_rate = payload.get("pass_rate")
    plan_name = payload.get("plan_name")
    report_url = payload.get("report_url")

    segments = [f"[{project}] {entity_type} {entity_name} finished with status {status}"]
    if pass_rate is not None:
        try:
            numeric = float(pass_rate) * 100 if pass_rate <= 1 else float(pass_rate)
            segments.append(f"Pass rate: {numeric:.1f}%")
        except (TypeError, ValueError):  # pragma: no cover - defensive
            segments.append(f"Pass rate: {pass_rate}")
    if plan_name:
        segments.append(f"Execution Plan: {plan_name}")
    if report_url:
        segments.append(f"Report: {report_url}")

    return "\n".join(segments)


__all__ = ["render_run_finished_message"]
