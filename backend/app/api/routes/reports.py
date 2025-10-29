from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import get_current_user
from app.core.config import get_settings
from app.core.errors import ErrorCode, http_exception
from app.db.session import get_db
from app.logging import get_logger
from app.models import ProjectMember, TestReport, User
from app.models.ai_task import AITask, TaskStatus, TaskType
from app.models.test_report import ReportEntityType, ReportStatus
from app.schemas.test_report import ReportSummarizeRequest, TestReportRead
from app.services.ai import get_ai_provider
from app.services.ai.base import AIProviderError
from app.services.reports.formatter import format_report_detail, format_report_summary
from app.tasks import celery_app

router = APIRouter(tags=["reports"])
_logger = get_logger().bind(component="reports_routes")

_ALLOWED_ORDER_FIELDS: dict[str, Any] = {
    "started_at": TestReport.started_at,
    "finished_at": TestReport.finished_at,
    "created_at": TestReport.created_at,
    "duration_ms": TestReport.duration_ms,
}


@router.get("/reports", response_model=ResponseEnvelope)
def list_reports(
    project_id: UUID = Query(..., description="Filter by project"),
    entity_type: ReportEntityType | None = Query(None, description="Entity type filter"),
    status_filter: ReportStatus | None = Query(None, alias="status", description="Status filter"),
    date_from: datetime | None = Query(None, description="Filter reports started after this date"),
    date_to: datetime | None = Query(None, description="Filter reports started before this date"),
    duration_ms_min: int | None = Query(None, ge=0, description="Minimum duration filter"),
    duration_ms_max: int | None = Query(None, ge=0, description="Maximum duration filter"),
    order_by: str = Query("started_at", description="Ordering field"),
    order_direction: Literal["asc", "desc"] = Query("desc", description="Ordering direction"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _ensure_membership(db, project_id, current_user.id)

    query = select(TestReport).where(
        TestReport.project_id == project_id,
        TestReport.is_deleted.is_(False),
    )

    if entity_type is not None:
        query = query.where(TestReport.entity_type == entity_type)
    if status_filter is not None:
        query = query.where(TestReport.status == status_filter)
    if date_from is not None:
        query = query.where(TestReport.started_at >= date_from)
    if date_to is not None:
        query = query.where(TestReport.started_at <= date_to)
    if duration_ms_min is not None:
        query = query.where(TestReport.duration_ms >= duration_ms_min)
    if duration_ms_max is not None:
        query = query.where(TestReport.duration_ms <= duration_ms_max)

    total_stmt = select(func.count()).select_from(query.subquery())
    total = db.execute(total_stmt).scalar_one()

    order_column = _resolve_order_column(order_by)
    if order_direction.lower() == "asc":
        query = query.order_by(order_column.asc())
    else:
        query = query.order_by(order_column.desc())

    offset = (page - 1) * page_size
    records = db.execute(query.offset(offset).limit(page_size)).scalars().all()

    settings = get_settings()
    items = [format_report_summary(report, settings=settings) for report in records]

    payload = {
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
        },
    }
    return success_response(payload)


@router.get("/reports/{report_id}", response_model=ResponseEnvelope)
def get_report(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    report = _get_report_or_404(db, report_id)
    _ensure_membership(db, report.project_id, current_user.id)

    settings = get_settings()
    payload = format_report_detail(report, settings=settings)
    return success_response(payload)


@router.post("/reports/{report_id}/summarize", response_model=ResponseEnvelope)
def summarize_report(
    report_id: UUID,
    body: ReportSummarizeRequest,
    provider_key: str | None = Query(default=None, alias="provider"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    provider = get_ai_provider(provider_key)
    report = _get_report_or_404(db, report_id)
    _ensure_membership(db, report.project_id, current_user.id)

    if report.summary is not None and not body.overwrite:
        return success_response(
            {
                "report_id": str(report.id),
                "summary": report.summary,
                "task_id": None,
                "updated": False,
            }
        )

    report_payload = _serialize_report(report)
    input_payload = {
        "report_id": str(report.id),
        "project_id": str(report.project_id),
        "report": report_payload,
    }
    task = _create_ai_task(
        db,
        project_id=report.project_id,
        provider_name=provider.provider_name,
        input_payload=input_payload,
    )

    try:
        result = provider.summarize_report(report_payload)
    except AIProviderError as exc:
        _resolve_task_failure(db, task, exc.message)
        raise http_exception(exc.status_code, exc.code, exc.message, data=exc.data) from exc
    except Exception as exc:  # pragma: no cover - safeguard
        _logger.error("report_summary_unexpected_error", report_id=str(report_id), error=str(exc))
        _resolve_task_failure(db, task, str(exc))
        raise http_exception(
            status.HTTP_502_BAD_GATEWAY,
            ErrorCode.AI_PROVIDER_ERROR,
            "Failed to summarize report",
            data={"task_id": str(task.id)},
        ) from exc

    markdown_payload = result.payload.get("markdown") if isinstance(result.payload, dict) else None
    if not isinstance(markdown_payload, str) or not markdown_payload.strip():
        _resolve_task_failure(db, task, "Provider returned an empty summary")
        raise http_exception(
            status.HTTP_502_BAD_GATEWAY,
            ErrorCode.AI_PROVIDER_ERROR,
            "Provider returned an empty summary",
            data={"task_id": str(task.id)},
        )

    task.status = TaskStatus.SUCCESS
    task.output_payload = result.payload
    task.error_message = None
    task.model = result.model
    if result.usage:
        task.prompt_tokens = result.usage.prompt_tokens
        task.completion_tokens = result.usage.completion_tokens
        task.total_tokens = result.usage.total_tokens
    else:
        task.prompt_tokens = None
        task.completion_tokens = None
        task.total_tokens = None

    report.summary = markdown_payload.strip()
    db.add(task)
    db.add(report)
    db.commit()
    db.refresh(task)
    db.refresh(report)

    return success_response(
        {
            "report_id": str(report.id),
            "summary": report.summary,
            "task_id": str(task.id),
            "updated": True,
        }
    )


@router.get("/reports/{report_id}/export", response_model=ResponseEnvelope)
def export_report(
    report_id: UUID,
    format: Literal["markdown", "pdf"] = Query("markdown", description="Export format"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    report = _get_report_or_404(db, report_id)
    _ensure_membership(db, report.project_id, current_user.id)

    settings = get_settings()
    detail = format_report_detail(report, settings=settings)

    if format == "markdown":
        markdown = _build_markdown_export(detail)
        response_data = {
            "report_id": str(report.id),
            "format": "markdown",
            "filename": f"report-{report.id}.md",
            "content_type": "text/markdown",
            "content": markdown,
        }
        return success_response(response_data)

    raise http_exception(
        status.HTTP_501_NOT_IMPLEMENTED,
        ErrorCode.REPORT_EXPORT_UNSUPPORTED,
        "PDF export is not currently supported",
    )


@router.get("/metrics/reports/summary", response_model=ResponseEnvelope)
def metrics_reports_summary(
    project_id: UUID = Query(..., description="Project identifier"),
    days: int = Query(14, ge=1, le=90, description="Number of days to aggregate"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _ensure_membership(db, project_id, current_user.id)

    now = datetime.now(timezone.utc)
    start_date = (now.date() - timedelta(days=days - 1)) if days > 0 else now.date()
    start_dt = datetime.combine(start_date, time.min).replace(tzinfo=timezone.utc)

    stmt = (
        select(func.date(TestReport.started_at), TestReport.status, func.count())
        .where(
            TestReport.project_id == project_id,
            TestReport.is_deleted.is_(False),
            TestReport.started_at >= start_dt,
        )
        .group_by(func.date(TestReport.started_at), TestReport.status)
    )

    results = db.execute(stmt).all()

    buckets: dict[str, dict[str, int]] = {}
    for day_value, status_value, count in results:
        day_key = day_value.isoformat()
        bucket = buckets.setdefault(day_key, {"passed": 0, "failed": 0, "error": 0})
        if status_value == ReportStatus.PASSED:
            bucket["passed"] += count
        elif status_value == ReportStatus.FAILED:
            bucket["failed"] += count
        elif status_value == ReportStatus.ERROR:
            bucket["error"] += count

    series: list[dict[str, Any]] = []
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        key = day.isoformat()
        bucket = buckets.get(key, {"passed": 0, "failed": 0, "error": 0})
        total = bucket["passed"] + bucket["failed"] + bucket["error"]
        success_rate = round(bucket["passed"] / total, 4) if total else 0.0
        series.append(
            {
                "date": key,
                "passed": bucket["passed"],
                "failed": bucket["failed"],
                "error": bucket["error"],
                "success_rate": success_rate,
            }
        )

    payload = {
        "project_id": str(project_id),
        "from": start_date.isoformat(),
        "to": now.date().isoformat(),
        "days": days,
        "series": series,
    }
    return success_response(payload)


@router.get("/tasks/{task_id}", response_model=ResponseEnvelope, tags=["tasks"])
def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    async_result = celery_app.AsyncResult(task_id)
    report = _find_report_by_task_id(db, task_id)
    report_id: UUID | None = None
    report_url: str | None = None
    if report is not None:
        _ensure_membership(db, report.project_id, current_user.id)
        report_id = report.id
        report_url = f"/reports/{report.id}"
    status_value = async_result.status.lower() if async_result.status else "pending"
    payload = {
        "task_id": task_id,
        "status": status_value,
        "report_id": report_id,
        "report_url": report_url,
    }
    return success_response(payload)


def _resolve_order_column(order_by: str) -> Any:
    key = (order_by or "started_at").strip().lower()
    column = _ALLOWED_ORDER_FIELDS.get(key)
    if column is None:
        raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "Unsupported order_by field")
    return column


def _get_report_or_404(db: Session, report_id: UUID) -> TestReport:
    report = db.get(TestReport, report_id)
    if report is None or report.is_deleted:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.REPORT_NOT_FOUND, "Report not found")
    return report


def _ensure_membership(db: Session, project_id: UUID, user_id: UUID) -> None:
    stmt = (
        select(ProjectMember)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
            ProjectMember.is_deleted.is_(False),
        )
        .limit(1)
    )
    membership = db.execute(stmt).scalar_one_or_none()
    if membership is None:
        raise http_exception(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.NO_PERMISSION,
            "You do not have access to this project",
        )


def _find_report_by_task_id(db: Session, task_id: str) -> TestReport | None:
    stmt = select(TestReport).where(TestReport.is_deleted.is_(False))
    reports = db.execute(stmt).scalars().all()
    for report in reports:
        metrics = report.metrics or {}
        if str(metrics.get("task_id")) == task_id:
            return report
    return None


def _create_ai_task(
    db: Session,
    *,
    project_id: UUID,
    provider_name: str,
    input_payload: dict[str, Any],
) -> AITask:
    task = AITask(
        project_id=project_id,
        task_type=TaskType.SUMMARIZE_REPORT,
        provider=provider_name,
        status=TaskStatus.PENDING,
        input_payload=input_payload,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _resolve_task_failure(db: Session, task: AITask, message: str) -> None:
    task.status = TaskStatus.FAILED
    task.error_message = message
    task.model = None
    task.prompt_tokens = None
    task.completion_tokens = None
    task.total_tokens = None
    db.add(task)
    db.commit()


def _serialize_report(report: TestReport) -> dict[str, Any]:
    schema = TestReportRead.model_validate(report)
    return schema.model_dump(mode="json")


def _build_markdown_export(report: dict[str, Any]) -> str:
    duration_ms = report.get("duration_ms")
    duration_display = f"{duration_ms} ms" if duration_ms is not None else "N/A"
    pass_rate = report.get("pass_rate")
    pass_rate_display = f"{round(pass_rate * 100)}%" if isinstance(pass_rate, (int, float)) else "0%"

    lines = [
        f"# Test Report {report['id']}",
        "",
        "## Overview",
        f"- Project ID: {report['project_id']}",
        f"- Entity Type: {report['entity_type']}",
        f"- Entity ID: {report['entity_id']}",
        f"- Status: {report['status']}",
        f"- Started At: {report['started_at']}",
        f"- Finished At: {report.get('finished_at') or 'N/A'}",
        f"- Duration: {duration_display}",
        f"- Assertions: {report.get('assertions_passed', 0)}/{report.get('assertions_total', 0)}",
        f"- Pass Rate: {pass_rate_display}",
        f"- Response Size: {report.get('response_size', 0)} bytes",
        "",
        "## AI Summary",
    ]

    summary_text = report.get("summary")
    if summary_text:
        lines.append(summary_text)
    else:
        lines.append("_No AI summary has been generated for this report._")

    lines.extend(
        [
            "",
            "## Notes",
        ]
    )

    if report.get("response_payload_truncated"):
        note = report.get("response_payload_note") or "Response payload was truncated due to size limits."
        lines.append(f"- {note}")
    if report.get("request_payload_truncated"):
        note = report.get("request_payload_note") or "Request payload was truncated due to size limits."
        lines.append(f"- {note}")
    if report.get("response_payload_truncated") is False and report.get("request_payload_truncated") is False:
        lines.append("- No truncation applied to request or response payloads.")

    return "\n".join(lines)
