from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.logging import get_logger
from app.models import ExecutionPlan, Notifier, NotifierEvent, NotifierEventStatus, NotifierEventType, Project, TestCase, TestSuite
from app.models.notifier import NotifierType
from app.models.test_report import ReportEntityType, TestReport
from app.services.notify.templates import render_run_finished_message
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

    payload["message"] = render_run_finished_message(payload)
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
        event = NotifierEvent(
            project_id=report.project_id,
            notifier_id=notifier.id,
            event=NotifierEventType.RUN_FINISHED,
            payload=payload,
            status=NotifierEventStatus.PENDING,
        )
        event.created_at = now  # ensure deterministic timestamps for tests
        session.add(event)
        events.append(event)

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
