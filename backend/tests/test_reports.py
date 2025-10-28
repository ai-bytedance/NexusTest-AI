from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ai_task import AITask, TaskType
from app.models.test_report import ReportEntityType, ReportStatus, TestReport
from app.services.ai.registry import get_ai_provider
from tests.test_projects import auth_headers, register_and_login


def _create_report(
    db: Session,
    *,
    project_id: uuid.UUID,
    status: ReportStatus,
    started_at: datetime,
    duration_ms: int = 1000,
    request_payload: dict | None = None,
    response_payload: dict | None = None,
    assertions: list[dict] | None = None,
    summary: str | None = None,
) -> TestReport:
    report = TestReport(
        project_id=project_id,
        entity_type=ReportEntityType.CASE,
        entity_id=uuid.uuid4(),
        status=status,
        started_at=started_at,
        finished_at=started_at + timedelta(milliseconds=duration_ms),
        duration_ms=duration_ms,
        request_payload=request_payload or {"payload": True},
        response_payload=response_payload or {"data": "ok"},
        assertions_result={"results": assertions or []},
        metrics={"task_id": f"task-{uuid.uuid4()}"},
        summary=summary,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def test_reports_listing_filters_and_pagination(client: TestClient, db_session: Session) -> None:
    token = register_and_login(client, "reports-list@example.com")
    project_response = client.post(
        "/api/v1/projects",
        json={"name": "Reporting", "key": "RPT", "description": "Reports"},
        headers=auth_headers(token),
    )
    assert project_response.status_code == 200, project_response.text
    project_id = uuid.UUID(project_response.json()["data"]["id"])

    base_time = datetime.now(timezone.utc)
    _create_report(
        db_session,
        project_id=project_id,
        status=ReportStatus.PASSED,
        started_at=base_time - timedelta(hours=1),
        assertions=[{"passed": True}, {"passed": True}],
    )
    _create_report(
        db_session,
        project_id=project_id,
        status=ReportStatus.FAILED,
        started_at=base_time,
        duration_ms=2500,
        assertions=[{"passed": True}, {"passed": False}],
    )
    _create_report(
        db_session,
        project_id=project_id,
        status=ReportStatus.ERROR,
        started_at=base_time - timedelta(days=1),
        duration_ms=4000,
        assertions=[{"passed": False}],
    )

    response = client.get(
        "/api/v1/reports",
        params={"project_id": str(project_id), "page_size": 2},
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["pagination"]["total"] == 3
    assert len(payload["items"]) == 2
    first_started = datetime.fromisoformat(payload["items"][0]["started_at"])
    second_started = datetime.fromisoformat(payload["items"][1]["started_at"])
    assert first_started >= second_started

    filtered = client.get(
        "/api/v1/reports",
        params={"project_id": str(project_id), "status": "passed"},
        headers=auth_headers(token),
    )
    assert filtered.status_code == 200, filtered.text
    filtered_payload = filtered.json()["data"]
    assert filtered_payload["pagination"]["total"] == 1
    item = filtered_payload["items"][0]
    assert item["status"] == "passed"
    assert item["assertions_total"] == 2
    assert item["assertions_passed"] == 2

    duration_filtered = client.get(
        "/api/v1/reports",
        params={"project_id": str(project_id), "duration_ms_min": 3000},
        headers=auth_headers(token),
    )
    assert duration_filtered.status_code == 200, duration_filtered.text
    duration_payload = duration_filtered.json()["data"]
    assert duration_payload["pagination"]["total"] == 1
    assert duration_payload["items"][0]["status"] == "error"


def test_report_detail_redaction_and_truncation(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAX_RESPONSE_SIZE_BYTES", "128")
    monkeypatch.setenv("REDACT_FIELDS", "token,password,secret")
    get_settings.cache_clear()

    token = register_and_login(client, "reports-detail@example.com")
    project_response = client.post(
        "/api/v1/projects",
        json={"name": "Secure", "key": "SEC", "description": "Secure reports"},
        headers=auth_headers(token),
    )
    assert project_response.status_code == 200, project_response.text
    project_id = uuid.UUID(project_response.json()["data"]["id"])

    report = _create_report(
        db_session,
        project_id=project_id,
        status=ReportStatus.PASSED,
        started_at=datetime.now(timezone.utc),
        request_payload={"token": "secret-token", "nested": {"password": "s3cr3t"}},
        response_payload={"data": "x" * 1024, "secret": "should-hide"},
        assertions=[{"passed": True}, {"passed": False}],
    )

    response = client.get(
        f"/api/v1/reports/{report.id}",
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    detail = response.json()["data"]
    assert detail["request_payload"]["token"] == "***"
    assert detail["request_payload"]["nested"]["password"] == "***"
    assert detail["response_payload"]["_truncated"] is True
    assert detail["response_payload_truncated"] is True
    assert "exceeded" in detail["response_payload_note"]
    assert detail["response_size"] > 128
    assert detail["assertions_total"] == 2
    assert detail["assertions_passed"] == 1

    get_settings.cache_clear()


def test_report_summarize_is_idempotent(client: TestClient, db_session: Session) -> None:
    get_settings.cache_clear()
    get_ai_provider.cache_clear()

    token = register_and_login(client, "reports-summary@example.com")
    project_response = client.post(
        "/api/v1/projects",
        json={"name": "Summaries", "key": "SUM", "description": "Summary project"},
        headers=auth_headers(token),
    )
    assert project_response.status_code == 200, project_response.text
    project_id = uuid.UUID(project_response.json()["data"]["id"])

    report = _create_report(
        db_session,
        project_id=project_id,
        status=ReportStatus.PASSED,
        started_at=datetime.now(timezone.utc),
        assertions=[{"passed": True}],
    )

    first = client.post(
        f"/api/v1/reports/{report.id}/summarize",
        json={"overwrite": False},
        headers=auth_headers(token),
    )
    assert first.status_code == 200, first.text
    first_payload = first.json()["data"]
    assert first_payload["updated"] is True
    assert first_payload["task_id"]
    assert first_payload["summary"].startswith("## Test Execution Summary")

    db_session.refresh(report)
    assert report.summary == first_payload["summary"]

    second = client.post(
        f"/api/v1/reports/{report.id}/summarize",
        json={"overwrite": False},
        headers=auth_headers(token),
    )
    assert second.status_code == 200, second.text
    second_payload = second.json()["data"]
    assert second_payload["updated"] is False
    assert second_payload["task_id"] is None
    assert second_payload["summary"] == first_payload["summary"]

    task_stmt = select(AITask).where(AITask.project_id == project_id, AITask.task_type == TaskType.SUMMARIZE_REPORT)
    tasks = db_session.execute(task_stmt).scalars().all()
    assert len(tasks) == 1

    get_ai_provider.cache_clear()
    get_settings.cache_clear()


def test_report_export_markdown_and_pdf_stub(client: TestClient, db_session: Session) -> None:
    token = register_and_login(client, "reports-export@example.com")
    project_response = client.post(
        "/api/v1/projects",
        json={"name": "Export", "key": "EXP", "description": "Export project"},
        headers=auth_headers(token),
    )
    assert project_response.status_code == 200, project_response.text
    project_id = uuid.UUID(project_response.json()["data"]["id"])

    report = _create_report(
        db_session,
        project_id=project_id,
        status=ReportStatus.FAILED,
        started_at=datetime.now(timezone.utc),
        assertions=[{"passed": False}],
        summary="Sample summary",
    )

    markdown_response = client.get(
        f"/api/v1/reports/{report.id}/export",
        params={"format": "markdown"},
        headers=auth_headers(token),
    )
    assert markdown_response.status_code == 200, markdown_response.text
    markdown_payload = markdown_response.json()["data"]
    assert markdown_payload["format"] == "markdown"
    assert markdown_payload["content_type"] == "text/markdown"
    assert markdown_payload["content"].startswith("# Test Report")

    pdf_response = client.get(
        f"/api/v1/reports/{report.id}/export",
        params={"format": "pdf"},
        headers=auth_headers(token),
    )
    assert pdf_response.status_code == 501
    error_payload = pdf_response.json()
    assert error_payload["code"] == "R002"


def test_metrics_reports_summary(client: TestClient, db_session: Session) -> None:
    token = register_and_login(client, "reports-metrics@example.com")
    project_response = client.post(
        "/api/v1/projects",
        json={"name": "Metrics", "key": "MET", "description": "Metrics project"},
        headers=auth_headers(token),
    )
    assert project_response.status_code == 200, project_response.text
    project_id = uuid.UUID(project_response.json()["data"]["id"])

    now = datetime.now(timezone.utc)
    previous_day = now - timedelta(days=1)

    _create_report(
        db_session,
        project_id=project_id,
        status=ReportStatus.PASSED,
        started_at=previous_day.replace(hour=10, minute=0, second=0, microsecond=0),
        assertions=[{"passed": True}, {"passed": True}],
    )
    _create_report(
        db_session,
        project_id=project_id,
        status=ReportStatus.FAILED,
        started_at=previous_day.replace(hour=12, minute=0, second=0, microsecond=0),
        assertions=[{"passed": False}, {"passed": False}],
    )
    _create_report(
        db_session,
        project_id=project_id,
        status=ReportStatus.ERROR,
        started_at=now.replace(hour=9, minute=0, second=0, microsecond=0),
        assertions=[{"passed": False}],
    )

    response = client.get(
        "/api/v1/metrics/reports/summary",
        params={"project_id": str(project_id), "days": 3},
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["project_id"] == str(project_id)
    series = {entry["date"]: entry for entry in data["series"]}

    previous_key = previous_day.date().isoformat()
    today_key = now.date().isoformat()
    assert series[previous_key]["passed"] == 1
    assert series[previous_key]["failed"] == 1
    assert series[previous_key]["success_rate"] == 0.5
    assert series[today_key]["error"] == 1
