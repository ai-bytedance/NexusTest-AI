from __future__ import annotations

import uuid
from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.logging import get_logger
from app.models import AnalyticsFailCluster, TestReport
from app.models.test_report import ReportStatus
from app.observability.metrics import record_flaky_marked
from app.services.analytics.clusters import merge_clusters as _merge_clusters, split_cluster as _split_cluster, upsert_cluster
from app.services.analytics.flaky import compute_flakiness
from app.services.analytics.signature import build_failure_signature


class FailureAnalyticsProcessor:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._logger = get_logger().bind(component="failure_analytics")

    def process_pending(self, batch_size: int = 200) -> int:
        processed_signatures = self._process_failure_signatures(batch_size=batch_size)
        processed_flakiness = self._process_flakiness(batch_size=batch_size)
        total = processed_signatures + processed_flakiness
        if total:
            self._session.commit()
            self._logger.info(
                "analytics_processed_batch",
                signatures=processed_signatures,
                flakiness=processed_flakiness,
            )
        return total

    def recompute_project(self, project_id: uuid.UUID, batch_size: int = 200) -> int:
        reports = (
            self._session.execute(
                select(TestReport).where(
                    TestReport.project_id == project_id,
                    TestReport.is_deleted.is_(False),
                )
            )
            .scalars()
            .all()
        )
        for report in reports:
            report.failure_signature = None
            report.failure_excerpt = None
            report.is_flaky = False
            report.flakiness_score = None
            metrics = dict(report.metrics or {})
            analytics = metrics.get("analytics")
            if isinstance(analytics, dict):
                analytics.pop("flaky", None)
                if not analytics:
                    metrics.pop("analytics", None)
            report.metrics = metrics
            self._session.add(report)

        self._session.execute(delete(AnalyticsFailCluster).where(AnalyticsFailCluster.project_id == project_id))
        self._session.commit()

        total_processed = 0
        while True:
            processed = self._process_failure_signatures(batch_size=batch_size, project_id=project_id)
            if not processed:
                break
            total_processed += processed
            self._session.commit()
        while True:
            processed = self._process_flakiness(batch_size=batch_size, project_id=project_id)
            if not processed:
                break
            total_processed += processed
            self._session.commit()
        return total_processed

    def merge_clusters(self, target: AnalyticsFailCluster, sources: Iterable[AnalyticsFailCluster]) -> AnalyticsFailCluster:
        cluster = _merge_clusters(self._session, target=target, sources=sources)
        self._session.commit()
        return cluster

    def split_cluster(self, cluster: AnalyticsFailCluster, report_ids: Iterable[uuid.UUID]) -> None:
        _split_cluster(self._session, cluster=cluster, report_ids=report_ids)
        self._session.commit()

    def _process_failure_signatures(self, *, batch_size: int, project_id: uuid.UUID | None = None) -> int:
        stmt = (
            select(TestReport)
            .where(
                TestReport.is_deleted.is_(False),
                TestReport.status.in_([ReportStatus.FAILED, ReportStatus.ERROR]),
                TestReport.failure_signature.is_(None),
            )
            .order_by(TestReport.started_at.asc(), TestReport.created_at.asc())
            .limit(batch_size)
        )
        if project_id is not None:
            stmt = stmt.where(TestReport.project_id == project_id)
        reports = self._session.execute(stmt).scalars().all()
        processed = 0
        for report in reports:
            signature = build_failure_signature(report)
            if signature is None:
                report.failure_signature = None
                report.failure_excerpt = None
                self._session.add(report)
                continue
            report.failure_signature = signature.hash
            report.failure_excerpt = signature.excerpt
            upsert_cluster(self._session, report=report, signature=signature)
            self._session.add(report)
            processed += 1
        return processed

    def _process_flakiness(self, *, batch_size: int, project_id: uuid.UUID | None = None) -> int:
        stmt = (
            select(TestReport)
            .where(
                TestReport.is_deleted.is_(False),
                TestReport.flakiness_score.is_(None),
            )
            .order_by(TestReport.started_at.asc(), TestReport.created_at.asc())
            .limit(batch_size)
        )
        if project_id is not None:
            stmt = stmt.where(TestReport.project_id == project_id)
        reports = self._session.execute(stmt).scalars().all()
        if not reports:
            return 0

        processed = 0
        window = max(1, self._settings.analytics_window)
        for report in reports:
            result = compute_flakiness(self._session, report, window)
            previous_flag = bool(report.is_flaky)
            report.flakiness_score = result.score
            report.is_flaky = result.is_flaky
            metrics = dict(report.metrics or {})
            analytics = metrics.get("analytics")
            if not isinstance(analytics, dict):
                analytics = {}
            analytics["flaky"] = {**result.notes, "score": result.score, "is_flaky": result.is_flaky}
            metrics["analytics"] = analytics
            report.metrics = metrics
            self._session.add(report)
            if result.is_flaky and not previous_flag:
                record_flaky_marked(str(report.project_id), report.entity_type.value)
            processed += 1
        return processed
