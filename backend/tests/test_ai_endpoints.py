from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ai_task import AITask, TaskStatus, TaskType
from app.services.ai import clear_ai_provider_cache
from app.services.ai.providers.mock import MockProvider
from tests.test_projects import auth_headers, register_and_login


def reset_provider_cache(monkeypatch: MonkeyPatch, provider_name: str) -> None:
    monkeypatch.setenv("PROVIDER", provider_name)
    get_settings.cache_clear()
    clear_ai_provider_cache()


def test_mock_provider_outputs_are_deterministic() -> None:
    provider = MockProvider()
    spec = {"path": "/users", "method": "GET"}
    response = {"status": "ok", "data": {"id": 1}}
    schema = {"type": "object", "properties": {"id": {"type": "string"}}}

    cases_first = provider.generate_test_cases(spec)
    cases_second = provider.generate_test_cases(spec)
    assert cases_first == cases_second
    assert "cases" in cases_first

    assertions_first = provider.generate_assertions(response)
    assertions_second = provider.generate_assertions(response)
    assert assertions_first == assertions_second
    assert "assertions" in assertions_first

    mock_data_first = provider.generate_mock_data(schema)
    mock_data_second = provider.generate_mock_data(schema)
    assert mock_data_first == mock_data_second
    assert "data" in mock_data_first

    summary = provider.summarize_report({"status": "passed"})
    assert summary.startswith("## Test Execution Summary")


def test_ai_endpoints_with_mock_provider(
    client: TestClient,
    db_session: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    reset_provider_cache(monkeypatch, "mock")

    token = register_and_login(client, "ai-user@example.com")

    project_response = client.post(
        "/api/v1/projects",
        json={"name": "AI Demo", "key": "AIDEMO", "description": "AI tests"},
        headers=auth_headers(token),
    )
    assert project_response.status_code == 200, project_response.text
    project_id = project_response.json()["data"]["id"]

    cases_response = client.post(
        "/api/v1/ai/generate-cases?provider=mock",
        json={"project_id": project_id, "api_spec": {"path": "/users", "method": "GET"}},
        headers=auth_headers(token),
    )
    assert cases_response.status_code == 200, cases_response.text
    cases_payload = cases_response.json()["data"]
    assert "cases" in cases_payload
    assert "task_id" in cases_payload

    assertions_response = client.post(
        "/api/v1/ai/generate-assertions",
        json={
            "project_id": project_id,
            "example_response": {"status": "success", "data": {"id": 1}},
        },
        headers=auth_headers(token),
    )
    assert assertions_response.status_code == 200, assertions_response.text
    assertions_payload = assertions_response.json()["data"]
    assert "assertions" in assertions_payload

    mock_data_response = client.post(
        "/api/v1/ai/mock-data",
        json={
            "project_id": project_id,
            "json_schema": {"type": "object", "properties": {"id": {"type": "string"}}},
        },
        headers=auth_headers(token),
    )
    assert mock_data_response.status_code == 200, mock_data_response.text
    mock_data_payload = mock_data_response.json()["data"]
    assert "data" in mock_data_payload

    summarize_response = client.post(
        "/api/v1/ai/summarize-report",
        json={
            "project_id": project_id,
            "report": {"status": "passed", "metrics": {"total": 4, "passed": 4, "failed": 0}},
        },
        headers=auth_headers(token),
    )
    assert summarize_response.status_code == 200, summarize_response.text
    summary_payload = summarize_response.json()["data"]
    assert "markdown" in summary_payload

    tasks = db_session.execute(select(AITask).order_by(AITask.created_at)).scalars().all()
    assert len(tasks) == 4
    assert {task.task_type for task in tasks} == {
        TaskType.GENERATE_CASES,
        TaskType.GENERATE_ASSERTIONS,
        TaskType.GENERATE_MOCK,
        TaskType.SUMMARIZE_REPORT,
    }
    assert all(task.status == TaskStatus.SUCCESS for task in tasks)
    assert all(task.provider == "mock" for task in tasks)
    assert all(task.model == "mock-model" for task in tasks)
    assert all(task.prompt_tokens == 0 for task in tasks)
    assert all(task.completion_tokens == 0 for task in tasks)
    assert all(task.total_tokens == 0 for task in tasks)
    assert tasks[0].output_payload.get("cases")

    clear_ai_provider_cache()


@pytest.mark.skipif(not os.getenv("DEEPSEEK_API_KEY"), reason="DeepSeek credentials not configured")
def test_deepseek_smoke(
    client: TestClient,
    db_session: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    reset_provider_cache(monkeypatch, "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", os.environ["DEEPSEEK_API_KEY"])
    base_url = os.getenv("DEEPSEEK_BASE_URL")
    if base_url:
        monkeypatch.setenv("DEEPSEEK_BASE_URL", base_url)

    token = register_and_login(client, "deepseek@example.com")

    project_response = client.post(
        "/api/v1/projects",
        json={"name": "DeepSeek", "key": "DEEPSEEK", "description": "DeepSeek smoke"},
        headers=auth_headers(token),
    )
    assert project_response.status_code == 200, project_response.text
    project_id = project_response.json()["data"]["id"]

    response = client.post(
        "/api/v1/ai/generate-cases",
        json={"project_id": project_id, "api_spec": {"path": "/ping", "method": "GET"}},
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert "cases" in payload
    assert "task_id" in payload

    task = (
        db_session.execute(select(AITask).where(AITask.task_type == TaskType.GENERATE_CASES)).scalar_one()
    )
    assert task.status == TaskStatus.SUCCESS
    assert task.provider == "deepseek"

    clear_ai_provider_cache()
