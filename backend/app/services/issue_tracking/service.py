from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Integration, Issue, IssueLinkSource, IssueSyncState, Project, TestReport
from app.models.issue import ReportIssueLink
from app.schemas.integration import IntegrationConnectionStatus
from app.schemas.issue import IssueTemplatePayload
from app.services.issue_tracking.linkage import attach_pull_requests, normalize_pull_request_reference
from app.services.issue_tracking.providers import (
    IssueCreateData,
    IssueResult,
    IssueTrackerError,
    IssueTrackerProvider,
    get_provider,
)
from app.services.reports.formatter import format_report_summary


class _SafeDict(dict[str, Any]):
    def __missing__(self, key: str) -> str:  # pragma: no cover - fallback
        return "{" + key + "}"


def _report_relative_url(report: TestReport) -> str:
    return f"/reports/{report.id}"


def _render_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        try:
            return value.format_map(_SafeDict(context))
        except Exception:  # pragma: no cover - defensive guard
            return value
    if isinstance(value, list):
        return [_render_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: _render_value(item, context) for key, item in value.items()}
    return value


def _default_title(project: Project, report: TestReport, summary: dict[str, Any]) -> str:
    entity_label = summary.get("entity_id") or str(report.entity_id)
    status = report.status.value.upper()
    return f"[{project.name}] {report.entity_type.value.title()} {entity_label} {status}"


def _default_description(report: TestReport, summary: dict[str, Any]) -> str:
    lines = [
        f"Report {report.id} finished with status {report.status.value}",
        f"Entity ID: {summary.get('entity_id', report.entity_id)}",
        f"Run number: {summary.get('run_number')}",
        f"Retry attempt: {summary.get('retry_attempt')}",
        f"Pass rate: {summary.get('pass_rate')}",
        f"Report URL: {_report_relative_url(report)}",
    ]
    description = "\n".join(str(item) for item in lines if item is not None)
    if summary.get("summary"):
        description += "\n\nSummary:\n" + str(summary["summary"])
    return description


def _build_context(project: Project, report: TestReport, summary: dict[str, Any], *, category: str | None) -> dict[str, Any]:
    context: dict[str, Any] = {
        "project_id": str(project.id),
        "project_name": project.name,
        "project_key": project.key,
        "report_id": str(report.id),
        "report_status": report.status.value,
        "entity_type": report.entity_type.value,
        "entity_id": str(report.entity_id),
        "report_url": _report_relative_url(report),
        "summary": summary.get("summary"),
        "pass_rate": summary.get("pass_rate"),
        "run_number": summary.get("run_number"),
        "retry_attempt": summary.get("retry_attempt"),
        "category": category or "default",
    }
    context.update({f"summary_{key}": value for key, value in summary.items() if key not in context})
    return context


def build_issue_payload(
    project: Project,
    report: TestReport,
    *,
    template: IssueTemplatePayload | None,
    summary: dict[str, Any],
    category: str | None = None,
) -> IssueCreateData:
    resolved_template = template or IssueTemplatePayload()
    context = _build_context(project, report, summary, category=category)
    title = resolved_template.title or _default_title(project, report, summary)
    description = resolved_template.description or _default_description(report, summary)

    rendered_title = _render_value(title, context)
    rendered_description = _render_value(description, context)
    labels = list(_render_value(list(resolved_template.labels), context)) if resolved_template.labels else []
    assignees = list(_render_value(list(resolved_template.assignees), context)) if resolved_template.assignees else []
    components = list(_render_value(list(resolved_template.components), context)) if resolved_template.components else []
    fields = _render_value(dict(resolved_template.fields), context)
    metadata = _render_value(dict(resolved_template.metadata), context)
    status = resolved_template.status

    return IssueCreateData(
        title=str(rendered_title),
        description=str(rendered_description),
        labels=[str(item) for item in labels],
        assignees=[str(item) for item in assignees],
        components=[str(item) for item in components],
        status=str(status) if status else None,
        fields=fields if isinstance(fields, dict) else {},
        metadata=metadata if isinstance(metadata, dict) else {},
    )


def _ensure_project(session: Session, project_id: UUID) -> Project:
    project = session.get(Project, project_id)
    if project is None or project.is_deleted:
        raise IssueTrackerError("Project not found for issue creation")
    return project


def _checkpoint_occurrences(metadata: dict[str, Any], *, report: TestReport, source: IssueLinkSource) -> None:
    occurrences: list[dict[str, Any]] = list(metadata.get("occurrences") or [])
    occurrences.append(
        {
            "report_id": str(report.id),
            "status": report.status.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source.value,
        }
    )
    metadata["occurrences"] = occurrences


def create_issue_for_report(
    session: Session,
    integration: Integration,
    report: TestReport,
    *,
    template: IssueTemplatePayload | None,
    linked_by: UUID | None,
    source: IssueLinkSource,
    note: str | None = None,
    category: str | None = None,
    dedupe_key: str | None = None,
    metadata_overrides: dict[str, Any] | None = None,
) -> Issue:
    if not integration.enabled:
        raise IssueTrackerError("Integration is disabled")

    provider = get_provider(integration)
    provider.test_connection()

    project = _ensure_project(session, report.project_id)
    settings = get_settings()
    summary = format_report_summary(report, settings=settings)
    payload = build_issue_payload(project, report, template=template, summary=summary, category=category)

    result: IssueResult = provider.create_issue(payload)
    now = datetime.now(timezone.utc)

    metadata: dict[str, Any] = {
        "raw": result.raw,
        "template": template.model_dump() if template else {},
        "category": category,
        "entity_id": str(report.entity_id),
        "entity_type": report.entity_type.value,
        "report_id": str(report.id),
        "automation": source == IssueLinkSource.AUTO,
        "pass_streak": 0,
        "provider_operations": provider.operations,
    }
    _checkpoint_occurrences(metadata, report=report, source=source)
    if metadata_overrides:
        metadata.update(metadata_overrides)

    issue = Issue(
        project_id=report.project_id,
        integration_id=integration.id,
        provider=integration.provider.value,
        external_id=result.external_id,
        url=result.url,
        title=result.title,
        status=result.status,
        dedupe_key=dedupe_key,
        created_by=linked_by,
        metadata_=metadata,
        last_sync_at=now,
    )
    session.add(issue)
    session.flush()

    link_metadata = {"category": category, "source": source.value}
    link = ReportIssueLink(
        report_id=report.id,
        issue_id=issue.id,
        linked_by=linked_by,
        source=source,
        note=note,
        metadata_=link_metadata,
    )
    session.add(link)

    return issue


def link_issue_to_report(
    session: Session,
    issue: Issue,
    report: TestReport,
    *,
    linked_by: UUID | None,
    source: IssueLinkSource,
    note: str | None = None,
    metadata_updates: dict[str, Any] | None = None,
) -> ReportIssueLink:
    metadata = dict(issue.metadata_ or {})
    metadata.setdefault("pass_streak", 0)
    _checkpoint_occurrences(metadata, report=report, source=source)
    if metadata_updates:
        metadata.update(metadata_updates)

    issue.metadata_ = metadata
    issue.last_sync_at = datetime.now(timezone.utc)
    session.add(issue)

    link = ReportIssueLink(
        report_id=report.id,
        issue_id=issue.id,
        linked_by=linked_by,
        source=source,
        note=note,
        metadata_={"source": source.value, "note": note} if note else {"source": source.value},
    )
    session.add(link)
    session.flush()
    return link


def test_integration_connection(integration: Integration) -> IntegrationConnectionStatus:
    provider = get_provider(integration)
    provider.test_connection()
    return IntegrationConnectionStatus(ok=True, details={"provider": integration.provider.value})


def summarize_issue(issue: Issue, include_links: bool = False) -> dict[str, Any]:
    payload = {
        "id": issue.id,
        "project_id": issue.project_id,
        "integration_id": issue.integration_id,
        "provider": issue.provider,
        "external_id": issue.external_id,
        "url": issue.url,
        "title": issue.title,
        "status": issue.status,
        "sync_state": issue.sync_state.value if issue.sync_state else None,
        "dedupe_key": issue.dedupe_key,
        "created_by": issue.created_by,
        "external_created_at": issue.external_created_at,
        "last_sync_at": issue.last_sync_at,
        "last_webhook_at": issue.last_webhook_at,
        "last_error": issue.last_error,
        "metadata": issue.metadata_,
        "linked_prs": issue.linked_prs or [],
        "linked_commits": issue.linked_commits or [],
        "created_at": issue.created_at,
        "updated_at": issue.updated_at,
    }
    if include_links:
        payload["links"] = [
            {
                "id": link.id,
                "report_id": link.report_id,
                "issue_id": link.issue_id,
                "linked_by": link.linked_by,
                "source": link.source.value,
                "note": link.note,
                "metadata": link.metadata_,
                "created_at": link.created_at,
                "updated_at": link.updated_at,
            }
            for link in issue.links
            if not link.is_deleted
        ]
    return payload


def find_issue_by_external(
    session: Session,
    *,
    project_id: UUID,
    provider: str,
    external_id: str,
) -> Issue | None:
    stmt = (
        sa.select(Issue)
        .where(
            Issue.project_id == project_id,
            Issue.provider == provider,
            Issue.external_id == external_id,
            Issue.is_deleted.is_(False),
        )
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def increment_pass_streak(issue: Issue, report: TestReport) -> None:
    metadata = dict(issue.metadata_ or {})
    pass_streak = int(metadata.get("pass_streak", 0)) + 1
    metadata["pass_streak"] = pass_streak
    _checkpoint_occurrences(metadata, report=report, source=IssueLinkSource.AUTO)
    issue.metadata_ = metadata


def reset_pass_streak(issue: Issue) -> None:
    metadata = dict(issue.metadata_ or {})
    metadata["pass_streak"] = 0
    issue.metadata_ = metadata


def aggregate_occurrence_windows(issues: Iterable[Issue]) -> list[str]:
    return [issue.dedupe_key or "" for issue in issues if issue.dedupe_key]


__all__ = [
    "build_issue_payload",
    "create_issue_for_report",
    "link_issue_to_report",
    "test_integration_connection",
    "summarize_issue",
    "find_issue_by_external",
    "increment_pass_streak",
    "reset_pass_streak",
    "aggregate_occurrence_windows",
]
