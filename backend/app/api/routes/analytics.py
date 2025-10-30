from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import ProjectContext, get_current_user, get_project_context, require_project_member
from app.core.config import get_settings
from app.core.errors import ErrorCode, http_exception
from app.db.session import get_db
from app.models import AnalyticsFailCluster, ProjectRole, TestReport, User
from app.models.analytics_fail_cluster import AnalyticsFailClusterStatus
from app.models.test_report import ReportStatus
from app.schemas.analytics import (
    FailureClusterDetail,
    FailureClusterPoint,
    FailureClusterSummary,
    FailureClusterUpdateRequest,
    FlakyEntitySummary,
)
from app.services.analytics.processor import FailureAnalyticsProcessor
from app.services.reports.formatter import format_report_summary

router = APIRouter(prefix="/analytics", tags=["analytics"])

_SPARKLINE_DAYS = 7
_TIMELINE_DAYS = 30


@router.get("/projects/{project_id}/analytics/clusters", response_model=ResponseEnvelope)
def list_failure_clusters(  # noqa: D401
    status_filter: AnalyticsFailClusterStatus | None = Query(None, alias="status"),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    q: str | None = Query(None, min_length=1),
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """List failure clusters for a project."""
    project = context.project
    settings = get_settings()
    stmt = (
        select(AnalyticsFailCluster)
        .where(
            AnalyticsFailCluster.project_id == project.id,
            AnalyticsFailCluster.is_deleted.is_(False),
        )
        .order_by(AnalyticsFailCluster.last_seen_at.desc())
    )
    if status_filter is not None:
        stmt = stmt.where(AnalyticsFailCluster.status == status_filter)
    if date_from is not None:
        stmt = stmt.where(AnalyticsFailCluster.last_seen_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(AnalyticsFailCluster.last_seen_at <= date_to)
    if q:
        needle = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(AnalyticsFailCluster.title).like(needle))

    clusters = db.execute(stmt).scalars().all()
    min_count = max(1, settings.cluster_min_count)
    filtered = [cluster for cluster in clusters if (cluster.count or 0) >= min_count]

    sparkline_map = _load_sparkline_map(db, project.id, days=_SPARKLINE_DAYS)
    summaries: list[dict[str, Any]] = [
        _serialize_cluster_summary(cluster, sparkline_map)
        for cluster in filtered
    ]
    return success_response({"items": summaries})


@router.get("/clusters/{cluster_id}", response_model=ResponseEnvelope)
def get_failure_cluster(
    cluster_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    cluster = _get_cluster_or_404(db, cluster_id)
    get_project_context(project_id=cluster.project_id, db=db, current_user=current_user)
    detail = _serialize_cluster_detail(db, cluster)
    return success_response(detail)


@router.patch("/clusters/{cluster_id}", response_model=ResponseEnvelope)
def update_failure_cluster(
    cluster_id: UUID,
    payload: FailureClusterUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    cluster = _get_cluster_or_404(db, cluster_id)
    context = get_project_context(project_id=cluster.project_id, db=db, current_user=current_user)
    if context.membership.role != ProjectRole.ADMIN:
        raise http_exception(status.HTTP_403_FORBIDDEN, ErrorCode.NO_PERMISSION, "Project admin privileges are required")

    updates = payload.model_dump(exclude_none=True)
    if "status" in updates:
        cluster.status = updates["status"]
    if "title" in updates:
        cluster.title = updates["title"] or cluster.title
    if "pattern" in updates:
        cluster.pattern = updates["pattern"]

    processor = FailureAnalyticsProcessor(db, get_settings())
    merge_ids = payload.merge_source_ids or []
    if merge_ids:
        sources = (
            db.execute(
                select(AnalyticsFailCluster)
                .where(
                    AnalyticsFailCluster.project_id == cluster.project_id,
                    AnalyticsFailCluster.id.in_(merge_ids),
                    AnalyticsFailCluster.is_deleted.is_(False),
                )
            )
            .scalars()
            .all()
        )
        processor.merge_clusters(cluster, sources)

    remove_ids = payload.remove_report_ids or []
    if remove_ids:
        processor.split_cluster(cluster, remove_ids)
        processor.process_pending(batch_size=len(remove_ids))
    else:
        db.add(cluster)
        db.commit()

    db.refresh(cluster)
    detail = _serialize_cluster_detail(db, cluster)
    return success_response(detail)


@router.get("/projects/{project_id}/analytics/flaky", response_model=ResponseEnvelope)
def list_flaky_entities(  # noqa: D401
    top: int = Query(50, ge=1, le=200),
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """List the most flaky test entities for the project."""
    project = context.project
    stmt = (
        select(TestReport)
        .where(
            TestReport.project_id == project.id,
            TestReport.is_deleted.is_(False),
            TestReport.is_flaky.is_(True),
        )
        .order_by(TestReport.flakiness_score.desc(), TestReport.started_at.desc())
    )
    reports = db.execute(stmt).scalars().all()

    latest_by_entity: dict[tuple[str, UUID], TestReport] = {}
    for report in reports:
        key = (report.entity_type.value, report.entity_id)
        existing = latest_by_entity.get(key)
        if existing is None or (report.started_at or report.created_at) > (existing.started_at or existing.created_at):
            latest_by_entity[key] = report
    ordered = sorted(
        latest_by_entity.values(),
        key=lambda item: (item.flakiness_score or 0.0),
        reverse=True,
    )[:top]

    entity_names = _load_entity_names(db, ordered)
    sparkline_map = _load_entity_recent_map(db, project.id, ordered)
    summaries = [
        _serialize_flaky_entity(report, entity_names, sparkline_map)
        for report in ordered
    ]
    return success_response({"items": summaries})


@router.post("/projects/{project_id}/analytics/recompute", response_model=ResponseEnvelope)
def recompute_failure_analytics(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    context = get_project_context(project_id=project_id, db=db, current_user=current_user)
    if context.membership.role != ProjectRole.ADMIN:
        raise http_exception(status.HTTP_403_FORBIDDEN, ErrorCode.NO_PERMISSION, "Project admin privileges are required")

    processor = FailureAnalyticsProcessor(db, get_settings())
    processed = processor.recompute_project(project_id)
    return success_response({"processed": processed})


def _get_cluster_or_404(db: Session, cluster_id: UUID) -> AnalyticsFailCluster:
    cluster = db.get(AnalyticsFailCluster, cluster_id)
    if cluster is None or cluster.is_deleted:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Analytics cluster not found")
    return cluster


def _serialize_cluster_summary(cluster: AnalyticsFailCluster, sparkline_map: dict[str, list[int]]) -> dict[str, Any]:
    sample_ids: list[UUID] = []
    for item in cluster.sample_report_ids or []:
        try:
            sample_ids.append(UUID(str(item)))
        except (TypeError, ValueError):
            continue
    sparkline = sparkline_map.get(cluster.signature_hash)
    if sparkline is None:
        sparkline = [0] * _SPARKLINE_DAYS
    model = FailureClusterSummary(
        id=cluster.id,
        created_at=cluster.created_at,
        updated_at=cluster.updated_at,
        project_id=cluster.project_id,
        signature_hash=cluster.signature_hash,
        title=cluster.title,
        pattern=cluster.pattern,
        status=cluster.status,
        count=cluster.count or 0,
        first_seen_at=cluster.first_seen_at,
        last_seen_at=cluster.last_seen_at,
        sample_report_ids=sample_ids,
        recent_count=sum(sparkline),
        sparkline=sparkline,
    )
    return model.model_dump(mode="json")


def _serialize_cluster_detail(db: Session, cluster: AnalyticsFailCluster) -> dict[str, Any]:
    sparkline_map = _load_sparkline_map(db, cluster.project_id, days=_SPARKLINE_DAYS)
    summary = _serialize_cluster_summary(cluster, sparkline_map)

    reports_stmt = (
        select(TestReport)
        .where(
            TestReport.project_id == cluster.project_id,
            TestReport.failure_signature == cluster.signature_hash,
            TestReport.is_deleted.is_(False),
        )
        .order_by(TestReport.started_at.desc(), TestReport.created_at.desc())
        .limit(10)
    )
    reports = db.execute(reports_stmt).scalars().all()
    settings = get_settings()
    summary["sample_reports"] = [format_report_summary(report, settings=settings) for report in reports]

    timeline_stmt = (
        select(func.date(TestReport.started_at), func.count())
        .where(
            TestReport.project_id == cluster.project_id,
            TestReport.failure_signature == cluster.signature_hash,
            TestReport.is_deleted.is_(False),
            TestReport.started_at.is_not(None),
            TestReport.started_at >= datetime.now(timezone.utc) - timedelta(days=_TIMELINE_DAYS - 1),
        )
        .group_by(func.date(TestReport.started_at))
        .order_by(func.date(TestReport.started_at))
    )
    timeline_rows = db.execute(timeline_stmt).all()
    timeline_map = {row[0].isoformat(): row[1] for row in timeline_rows}
    timeline: list[FailureClusterPoint] = []
    today = datetime.now(timezone.utc).date()
    for offset in range(_TIMELINE_DAYS):
        day = today - timedelta(days=_TIMELINE_DAYS - offset - 1)
        key = day.isoformat()
        timeline.append(FailureClusterPoint(date=key, count=int(timeline_map.get(key, 0))))
    summary["timeline"] = [point.model_dump(mode="json") for point in timeline]
    detail = FailureClusterDetail.model_validate(summary)
    return detail.model_dump(mode="json")


def _load_sparkline_map(db: Session, project_id: UUID, *, days: int) -> dict[str, list[int]]:
    since = datetime.now(timezone.utc).date() - timedelta(days=days - 1)
    counts_stmt = (
        select(
            TestReport.failure_signature,
            func.date(TestReport.started_at),
            func.count(),
        )
        .where(
            TestReport.project_id == project_id,
            TestReport.is_deleted.is_(False),
            TestReport.failure_signature.is_not(None),
            TestReport.status.in_([ReportStatus.FAILED, ReportStatus.ERROR]),
            TestReport.started_at.is_not(None),
            TestReport.started_at >= datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc),
        )
        .group_by(TestReport.failure_signature, func.date(TestReport.started_at))
    )
    rows = db.execute(counts_stmt).all()
    day_keys = _build_day_keys(days)
    sparkline_map: dict[str, list[int]] = {}
    for signature, day_value, count in rows:
        if signature is None or day_value is None:
            continue
        entry = sparkline_map.setdefault(signature, {key: 0 for key in day_keys})
        entry[day_value.isoformat()] = int(count)
    return {signature: [mapping[key] for key in day_keys] for signature, mapping in sparkline_map.items()}


def _build_day_keys(days: int) -> list[str]:
    today = datetime.now(timezone.utc).date()
    return [(today - timedelta(days=days - index - 1)).isoformat() for index in range(days)]


def _load_entity_names(db: Session, reports: list[TestReport]) -> dict[tuple[str, UUID], str | None]:
    case_ids = {report.entity_id for report in reports if report.entity_type.value == "case"}
    suite_ids = {report.entity_id for report in reports if report.entity_type.value == "suite"}
    names: dict[tuple[str, UUID], str | None] = {}
    if case_ids:
        from app.models.test_case import TestCase

        case_stmt = select(TestCase.id, TestCase.name).where(TestCase.id.in_(case_ids))
        for entity_id, name in db.execute(case_stmt).all():
            names[("case", entity_id)] = name
    if suite_ids:
        from app.models.test_suite import TestSuite

        suite_stmt = select(TestSuite.id, TestSuite.name).where(TestSuite.id.in_(suite_ids))
        for entity_id, name in db.execute(suite_stmt).all():
            names[("suite", entity_id)] = name
    return names


def _load_entity_recent_map(
    db: Session,
    project_id: UUID,
    reports: list[TestReport],
) -> dict[tuple[str, UUID], list[dict[str, Any]]]:
    if not reports:
        return {}
    settings = get_settings()
    mapping: dict[tuple[str, UUID], list[dict[str, Any]]] = {}
    for report in reports:
        key = (report.entity_type.value, report.entity_id)
        stmt = (
            select(TestReport)
            .where(
                TestReport.project_id == project_id,
                TestReport.entity_type == report.entity_type,
                TestReport.entity_id == report.entity_id,
                TestReport.is_deleted.is_(False),
            )
            .order_by(TestReport.started_at.desc(), TestReport.created_at.desc())
            .limit(5)
        )
        history = db.execute(stmt).scalars().all()
        mapping[key] = [format_report_summary(item, settings=settings) for item in history]
    return mapping


def _serialize_flaky_entity(
    report: TestReport,
    names: dict[tuple[str, UUID], str | None],
    history_map: dict[tuple[str, UUID], list[dict[str, Any]]],
) -> dict[str, Any]:
    key = (report.entity_type.value, report.entity_id)
    notes = (report.metrics or {}).get("analytics", {}).get("flaky", {})
    summary = FlakyEntitySummary(
        entity_type=report.entity_type.value,
        entity_id=report.entity_id,
        latest_report_id=report.id,
        flakiness_score=report.flakiness_score or 0.0,
        is_flaky=bool(report.is_flaky),
        name=names.get(key),
        pass_count=int(notes.get("pass_count", 0)),
        fail_count=int(notes.get("fail_count", 0)),
        transitions=int(notes.get("transitions", 0)),
        recent_reports=history_map.get(key, []),
    )
    return summary.model_dump(mode="json")
