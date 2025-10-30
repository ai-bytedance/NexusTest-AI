from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AnalyticsFailCluster, AnalyticsFailClusterStatus, TestReport
from app.services.analytics.signature import FailureSignature
from app.observability.metrics import record_cluster_created

_MAX_SAMPLE_REPORTS = 20


def upsert_cluster(
    session: Session,
    *,
    report: TestReport,
    signature: FailureSignature,
    sample_limit: int = _MAX_SAMPLE_REPORTS,
) -> AnalyticsFailCluster:
    stmt = (
        select(AnalyticsFailCluster)
        .where(
            AnalyticsFailCluster.project_id == report.project_id,
            AnalyticsFailCluster.signature_hash == signature.hash,
            AnalyticsFailCluster.is_deleted.is_(False),
        )
        .limit(1)
    )
    cluster = session.execute(stmt).scalar_one_or_none()
    occurred_at = _report_timestamp(report)

    if cluster is None:
        cluster = AnalyticsFailCluster(
            project_id=report.project_id,
            signature_hash=signature.hash,
            title=signature.title,
            pattern=signature.pattern,
            sample_report_ids=[str(report.id)],
            count=1,
            first_seen_at=occurred_at,
            last_seen_at=occurred_at,
            status=AnalyticsFailClusterStatus.OPEN,
        )
        session.add(cluster)
        record_cluster_created(str(report.project_id))
        return cluster

    cluster.count = (cluster.count or 0) + 1
    cluster.last_seen_at = max(cluster.last_seen_at or occurred_at, occurred_at)
    if cluster.first_seen_at is None or cluster.first_seen_at > occurred_at:
        cluster.first_seen_at = occurred_at
    if not cluster.title and signature.title:
        cluster.title = signature.title
    if not cluster.pattern and signature.pattern:
        cluster.pattern = signature.pattern

    existing_samples = list(cluster.sample_report_ids or [])
    existing_samples.insert(0, str(report.id))
    cluster.sample_report_ids = _truncate_samples(existing_samples, sample_limit)
    session.add(cluster)
    return cluster


def merge_clusters(
    session: Session,
    *,
    target: AnalyticsFailCluster,
    sources: Iterable[AnalyticsFailCluster],
) -> AnalyticsFailCluster:
    for source in sources:
        if source.id == target.id:
            continue
        if source.project_id != target.project_id:
            raise ValueError("Cannot merge clusters from different projects")
        target.count = (target.count or 0) + (source.count or 0)
        target.first_seen_at = _min_datetime(target.first_seen_at, source.first_seen_at)
        target.last_seen_at = _max_datetime(target.last_seen_at, source.last_seen_at)
        if not target.pattern and source.pattern:
            target.pattern = source.pattern
        if not target.title and source.title:
            target.title = source.title
        combined_samples = list(target.sample_report_ids or []) + list(source.sample_report_ids or [])
        target.sample_report_ids = _truncate_samples(combined_samples, _MAX_SAMPLE_REPORTS)

        session.execute(
            update(TestReport)
            .where(
                TestReport.project_id == target.project_id,
                TestReport.failure_signature == source.signature_hash,
            )
            .values(failure_signature=target.signature_hash)
        )
        session.delete(source)

    session.add(target)
    return target


def split_cluster(
    session: Session,
    *,
    cluster: AnalyticsFailCluster,
    report_ids: Iterable[uuid.UUID],
) -> None:
    report_id_set = {uuid.UUID(str(report_id)) for report_id in report_ids}
    if not report_id_set:
        return

    session.execute(
        update(TestReport)
        .where(
            TestReport.project_id == cluster.project_id,
            TestReport.id.in_(report_id_set),
        )
        .values(failure_signature=None, failure_excerpt=None)
    )

    remaining = [sample for sample in (cluster.sample_report_ids or []) if uuid.UUID(str(sample)) not in report_id_set]
    cluster.sample_report_ids = remaining
    cluster.count = max(0, (cluster.count or 0) - len(report_id_set))
    session.add(cluster)


def _truncate_samples(samples: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for sample in samples:
        if sample is None:
            continue
        normalized = str(sample)
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
        if len(ordered) >= limit:
            break
    return ordered


def _report_timestamp(report: TestReport) -> datetime:
    if report.started_at is not None:
        return report.started_at
    if report.finished_at is not None:
        return report.finished_at
    if report.created_at is not None:
        return report.created_at
    return datetime.now(timezone.utc)


def _min_datetime(lhs: datetime | None, rhs: datetime | None) -> datetime | None:
    values = [value for value in (lhs, rhs) if value is not None]
    if not values:
        return None
    return min(values)


def _max_datetime(lhs: datetime | None, rhs: datetime | None) -> datetime | None:
    values = [value for value in (lhs, rhs) if value is not None]
    if not values:
        return None
    return max(values)
