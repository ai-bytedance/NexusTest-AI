from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.logging import get_logger
from app.models import ExecutionPlan, Notifier, NotifierEvent, NotifierEventStatus, NotifierEventType, Project, TestCase, TestSuite
from app.models.test_report import ReportEntityType, TestReport
from app.services.notify.templates import NotificationTemplate, render_run_finished_template
from app.services.reports.formatter import format_report_summary

logger = get_logger()


def _load_notifiers(session: Session, project_id: uuid.UUID) -> list[Notifier]:
    stmt = (
        select(Notifier)
        .where(
            Notifier.project_id == project_id,
            Notifier.enabled.is_(True),
            Notifier.is_deleted.is_(False),
        )
        .options(selectinload(Notifier.project))
    )
    return session.execute(stmt).scalars().unique().all()


def _normalize_status_filters(raw: Any) -> set[str]:
    statuses: set[str] = set()
    if raw is None:
        return statuses
    if isinstance(raw, str):
        candidates = raw.split(",")
    elif isinstance(raw, (list, tuple, set)):
        candidates = raw
    else:
        return statuses
    for item in candidates:
        if not isinstance(item, str):
            continue
        value = item.strip().lower()
        if value:
            statuses.add(value)
    return statuses


def _coerce_fraction(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric < 0:
        numeric = 0.0
    if numeric > 1:
        numeric = numeric / 100.0
    if numeric > 1:
        numeric = 1.0
    return max(min(numeric, 1.0), 0.0)



def _extract_pass_rate(payload: dict[str, Any]) -> float | None:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    candidates = (
        payload.get("pass_rate"),
        summary.get("pass_rate") if isinstance(summary, dict) else None,
    )
    for candidate in candidates:
        fraction = _coerce_fraction(candidate)
        if fraction is not None:
            return fraction
    return None


def _should_send_notification(notifier: Notifier, payload: dict[str, Any]) -> tuple[bool, str | None]:
    config = notifier.config if isinstance(notifier.config, dict) else {}
    triggers = config.get("triggers") if isinstance(config.get("triggers"), dict) else {}

    status_filters = _normalize_status_filters(config.get("statuses"))
    status_filters |= _normalize_status_filters(triggers.get("statuses"))

    if bool(config.get("only_on_failures") or triggers.get("only_on_failures")):
        status_filters |= {"failed", "error"}

    status = str(payload.get("status") or "").strip().lower()
    if status_filters and status not in status_filters:
        return False, "status_filter"

    threshold_value = (
        triggers.get("pass_rate_below")
        if triggers.get("pass_rate_below") is not None
        else config.get("pass_rate_below")
    )
    threshold = _coerce_fraction(threshold_value)
    if threshold is not None and threshold <= 0:
        threshold = None
    if threshold is not None:
        observed = _extract_pass_rate(payload)
        if observed is None:
            observed = 1.0
        if observed >= threshold:
            return False, "pass_rate_threshold"

    return True, None


def _resolve_entity_details(session: Session, report: TestReport) -> dict[str, Any]:
    entity_name: str | None = None
    if report.entity_type == ReportEntityType.SUITE:
        suite = session.get(TestSuite, report.entity_id)
        entity_name = suite.name if suite else None
    elif report.entity_type == ReportEntityType.CASE:
        case = session.get(TestCase, report.entity_id)
        entity_name = case.name if case else None

    project = session.get(Project, report.project_id)
    project_name = project.name if project else "Unknown Project"

    plan_id: uuid.UUID | None = None
    plan_name: str | None = None
    plan_identifier = (report.metrics or {}).get("execution_plan_id") if isinstance(report.metrics, dict) else None
    if plan_identifier:
        try:
            plan_uuid = uuid.UUID(str(plan_identifier))
        except (TypeError, ValueError):  # pragma: no cover - best effort
            plan_uuid = None
        if plan_uuid is not None:
            plan = session.get(ExecutionPlan, plan_uuid)
            if plan and not plan.is_deleted:
                plan_id = plan.id
                plan_name = plan.name

    return {
        "project_name": project_name,
        "entity_name": entity_name,
        "plan_id": plan_id,
        "plan_name": plan_name,
    }


def build_run_finished_payload(session: Session, report: TestReport) -> dict[str, Any]:
    from app.core.config import get_settings

    settings = get_settings()
    summary = format_report_summary(report, settings=settings)

    details = _resolve_entity_details(session, report)

    payload: dict[str, Any] = {
        "report_id": str(report.id),
        "project_id": str(report.project_id),
        "status": report.status.value,
        "entity_type": report.entity_type.value,
        "entity_id": str(report.entity_id),
        "summary": summary,
        "pass_rate": summary.get("pass_rate"),
        "project_name": details.get("project_name"),
        "entity_name": details.get("entity_name"),
        "plan_id": str(details.get("plan_id")) if details.get("plan_id") else None,
        "plan_name": details.get("plan_name"),
        "finished_at": summary.get("finished_at"),
        "report_url": _build_report_url(report),
    }

    template = render_run_finished_template(payload)
    if isinstance(template, NotificationTemplate):
        payload["message"] = template.text
        payload["text"] = template.text
        payload["markdown"] = template.markdown
        payload["locale"] = template.locale
    else:  # pragma: no cover - defensive
        payload["message"] = str(template)
    return payload


def _build_report_url(report: TestReport) -> str:
    # Construct a relative path that frontend can resolve. Callers can prepend their base URL.
    if report.entity_type == ReportEntityType.SUITE:
        return f"/reports/{report.id}"
    if report.entity_type == ReportEntityType.CASE:
        return f"/reports/{report.id}"
    return f"/reports/{report.id}"


def queue_run_finished_notifications(session: Session, report: TestReport) -> list[NotifierEvent]:
    notifiers = _load_notifiers(session, report.project_id)
    if not notifiers:
        return []

    payload = build_run_finished_payload(session, report)
    events: list[NotifierEvent] = []

    for notifier in notifiers:
        should_send, reason = _should_send_notification(notifier, payload)
        if not should_send:
            logger.info(
                "notifier_event_skipped",
                notifier_id=str(notifier.id),
                project_id=str(report.project_id),
                report_id=str(report.id),
                reason=reason or "unknown",
            )
            continue

        event_payload = dict(payload)
        event = NotifierEvent(
            project_id=report.project_id,
            notifier_id=notifier.id,
            event=NotifierEventType.RUN_FINISHED,
            payload=event_payload,
            status=NotifierEventStatus.PENDING,
        )
        session.add(event)
        events.append(event)

    if not events:
        logger.info(
            "notifier_events_skipped_all",
            project_id=str(report.project_id),
            report_id=str(report.id),
        )
        return []

    session.flush()

    for event in events:
        logger.info(
            "queued_notifier_event",
            notifier_id=str(event.notifier_id),
            event_id=str(event.id),
            report_id=str(report.id),
        )

    session.commit()

    from app.tasks.notifications import dispatch_notifier_event

    for event in events:
        dispatch_notifier_event.apply_async((str(event.id),))

    return events


__all__ = ["build_run_finished_payload", "queue_run_finished_notifications"]
