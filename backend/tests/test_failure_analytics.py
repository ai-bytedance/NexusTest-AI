from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AnalyticsFailCluster, Project, ProjectMember, ProjectRole, TestReport, User, UserRole
from app.models.test_report import ReportEntityType, ReportStatus
from app.services.analytics.signature import build_failure_signature
from app.services.analytics.processor import FailureAnalyticsProcessor


def _create_user(db: Session) -> User:
    user = User(email=f"user-{uuid.uuid4()}@example.com", hashed_password="hashed", role=UserRole.ADMIN)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_project(db: Session) -> Project:
    owner = _create_user(db)
    project = Project(name=f"Analytics-{uuid.uuid4().hex[:6]}", key=f"ANL{uuid.uuid4().hex[:3].upper()}", created_by=owner.id)
    db.add(project)
    db.commit()
    db.refresh(project)
    membership = ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectRole.ADMIN)
    db.add(membership)
    db.commit()
    return project


def _create_report(
    db: Session,
    *,
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    status: ReportStatus,
    started_at: datetime,
    passed: bool,
) -> TestReport:
    response_payload = {
        "status_code": 400,
        "json": {"error": "boom", "code": 12345},
        "body": {"text": "boom happened"},
    }
    assertion = {
        "name": "body_equals",
        "operator": "equals",
        "passed": passed,
        "expected": {"message": "ok"},
        "actual": {"message": "boom"},
        "path": "$.body.message",
    }
    report = TestReport(
        project_id=project_id,
        entity_type=ReportEntityType.CASE,
        entity_id=entity_id,
        status=status,
        started_at=started_at,
        finished_at=started_at + timedelta(milliseconds=500),
        duration_ms=500,
        request_payload={"method": "GET", "url": "https://service.example.com"},
        response_payload=response_payload,
        assertions_result={"results": [assertion]},
        metrics={},
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def test_failure_signature_consistency(db_session: Session) -> None:
    project = _create_project(db_session)
    entity_id = uuid.uuid4()
    started_at = datetime.now(timezone.utc)

    failing_report = _create_report(
        db_session,
        project_id=project.id,
        entity_id=entity_id,
        status=ReportStatus.FAILED,
        started_at=started_at,
        passed=False,
    )

    signature = build_failure_signature(failing_report)
    assert signature is not None
    assert signature.hash
    assert signature.title
    assert "expected" in signature.excerpt

    clone = _create_report(
        db_session,
        project_id=project.id,
        entity_id=entity_id,
        status=ReportStatus.FAILED,
        started_at=started_at + timedelta(minutes=1),
        passed=False,
    )
    signature_clone = build_failure_signature(clone)
    assert signature_clone is not None
    assert signature_clone.hash == signature.hash
    assert signature_clone.excerpt == signature.excerpt


def test_failure_analytics_processor_builds_clusters_and_flaky_scores(db_session: Session) -> None:
    settings = get_settings()
    project = _create_project(db_session)
    entity_id = uuid.uuid4()
    base_time = datetime.now(timezone.utc) - timedelta(minutes=10)

    # Create a sequence of reports with alternating results to trigger flakiness.
    statuses = [ReportStatus.FAILED, ReportStatus.PASSED, ReportStatus.FAILED, ReportStatus.PASSED, ReportStatus.FAILED]
    reports: list[TestReport] = []
    for index, status in enumerate(statuses):
        reports.append(
            _create_report(
                db_session,
                project_id=project.id,
                entity_id=entity_id,
                status=status,
                started_at=base_time + timedelta(minutes=index),
                passed=status == ReportStatus.PASSED,
            )
        )

    processor = FailureAnalyticsProcessor(db_session, settings)
    processed = processor.process_pending(batch_size=20)
    assert processed > 0

    db_session.expire_all()
    cluster_stmt = select(AnalyticsFailCluster).where(AnalyticsFailCluster.project_id == project.id)
    clusters = db_session.execute(cluster_stmt).scalars().all()
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.count == 3  # three failures in the sequence
    assert cluster.signature_hash == reports[-1].failure_signature
    assert len(cluster.sample_report_ids) <= 20

    # Reload latest report to inspect flakiness annotations.
    latest_report = db_session.get(TestReport, reports[-1].id)
    assert latest_report is not None
    assert latest_report.is_flaky is True
    assert latest_report.flakiness_score is not None and latest_report.flakiness_score >= 0.5
    analytics_notes = (latest_report.metrics or {}).get("analytics", {}).get("flaky")
    assert isinstance(analytics_notes, dict)
    assert analytics_notes.get("fail_count") == 3
    assert analytics_notes.get("pass_count") == 2
