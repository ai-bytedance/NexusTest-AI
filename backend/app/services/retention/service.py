from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.logging import get_logger
from app.models import AITask, AuditLog, TestReport

logger = get_logger()


@dataclass
class RetentionStats:
    reports_scanned: int = 0
    reports_compacted: int = 0
    reports_archived: int = 0
    ai_tasks_deleted: int = 0
    audit_logs_deleted: int = 0


class RetentionService:
    def __init__(self, session: Session, settings: Optional[Settings] = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self._archive_dir = (
            Path(self.settings.report_archive_dir).expanduser()
            if self.settings.report_archive_dir
            else None
        )

    def purge(self, batch_size: int = 200) -> RetentionStats:
        stats = RetentionStats()
        stats.reports_scanned, stats.reports_compacted, stats.reports_archived = self._purge_reports(batch_size=batch_size)
        stats.ai_tasks_deleted = self._purge_ai_tasks()
        stats.audit_logs_deleted = self._purge_audit_logs()

        logger.info(
            "retention_completed",
            reports_scanned=stats.reports_scanned,
            reports_compacted=stats.reports_compacted,
            reports_archived=stats.reports_archived,
            ai_tasks_deleted=stats.ai_tasks_deleted,
            audit_logs_deleted=stats.audit_logs_deleted,
        )
        return stats

    # Reports -----------------------------------------------------------------

    def _purge_reports(self, batch_size: int) -> tuple[int, int, int]:
        retention_days = self.settings.report_retention_days
        if retention_days <= 0:
            return (0, 0, 0)

        _ = batch_size  # hint intentional unused parameter for future batching

        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        reports = (
            self.session.execute(
                select(TestReport).where(
                    TestReport.is_deleted.is_(False),
                    or_(
                        and_(TestReport.finished_at.is_not(None), TestReport.finished_at < cutoff),
                        and_(TestReport.finished_at.is_(None), TestReport.started_at < cutoff),
                    ),
                )
            )
            .scalars()
            .all()
        )
        if not reports:
            return (0, 0, 0)

        scanned = len(reports)
        compacted = 0
        archived = 0

        for report in reports:
            archive_uri = self._archive_report(report)
            if archive_uri:
                archived += 1
            self._compact_report(report, archive_uri)
            compacted += 1
            self.session.add(report)

        self.session.commit()

        return scanned, compacted, archived

    def _archive_report(self, report: TestReport) -> str | None:
        payload_size = self._payload_size(report)
        if payload_size < self.settings.report_archive_min_bytes:
            return None

        archive_payload = {
            "report_id": str(report.id),
            "project_id": str(report.project_id),
            "entity_type": report.entity_type.value,
            "request_payload": report.request_payload or {},
            "response_payload": report.response_payload or {},
            "assertions_result": report.assertions_result or {},
            "archived_at": datetime.now(timezone.utc).isoformat(),
        }

        uri: str | None = None
        if self._archive_dir:
            uri = self._archive_to_filesystem(report, archive_payload)

        remote_uri = self._archive_to_s3(report, archive_payload)
        if remote_uri:
            uri = remote_uri

        return uri

    def _archive_to_filesystem(self, report: TestReport, payload: dict) -> str:
        assert self._archive_dir is not None
        project_dir = self._archive_dir / str(report.project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{report.id}-{report.started_at.strftime('%Y%m%d%H%M%S')}.json"
        target = project_dir / filename
        with target.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        logger.info("report_archived_local", path=str(target))
        return str(target)

    def _archive_to_s3(self, report: TestReport, payload: dict) -> str | None:
        bucket = (self.settings.report_archive_s3_bucket or "").strip()
        if not bucket:
            return None
        try:
            import boto3  # type: ignore
        except ImportError:
            logger.warning("report_archive_s3_dependency_missing")
            return None

        prefix = self.settings.report_archive_s3_prefix
        key = f"{prefix}{report.project_id}/{report.id}.json" if prefix else f"{report.project_id}/{report.id}.json"
        client_kwargs: dict[str, object] = {}
        if self.settings.backup_s3_region:
            client_kwargs["region_name"] = self.settings.backup_s3_region
        if self.settings.backup_s3_endpoint_url:
            client_kwargs["endpoint_url"] = self.settings.backup_s3_endpoint_url
        if self.settings.backup_s3_access_key and self.settings.backup_s3_secret_key:
            client_kwargs["aws_access_key_id"] = self.settings.backup_s3_access_key
            client_kwargs["aws_secret_access_key"] = self.settings.backup_s3_secret_key
        client = boto3.client("s3", **client_kwargs)
        client.put_object(Bucket=bucket, Key=key, Body=json.dumps(payload).encode("utf-8"))
        uri = f"s3://{bucket}/{key}"
        logger.info("report_archived_remote", uri=uri)
        return uri

    def _compact_report(self, report: TestReport, archive_uri: str | None) -> None:
        metrics = dict(report.metrics or {})
        metrics["payload_compacted"] = True
        metrics["payload_compacted_at"] = datetime.now(timezone.utc).isoformat()
        if archive_uri:
            metrics["archive_uri"] = archive_uri
        report.request_payload = {}
        report.response_payload = {}
        report.assertions_result = {}
        report.metrics = metrics

    def _payload_size(self, report: TestReport) -> int:
        serialized = json.dumps(report.request_payload or {})
        serialized += json.dumps(report.response_payload or {})
        return len(serialized.encode("utf-8"))

    # Other entities ---------------------------------------------------------

    def _purge_ai_tasks(self) -> int:
        retention_days = self.settings.ai_task_retention_days
        if retention_days <= 0:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        result = self.session.execute(
            delete(AITask).where(AITask.created_at < cutoff)
        )
        self.session.commit()
        return int(result.rowcount or 0)

    def _purge_audit_logs(self) -> int:
        retention_days = self.settings.audit_log_retention_days
        if retention_days <= 0:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        result = self.session.execute(
            delete(AuditLog).where(AuditLog.created_at < cutoff)
        )
        self.session.commit()
        return int(result.rowcount or 0)


__all__ = ["RetentionService", "RetentionStats"]
