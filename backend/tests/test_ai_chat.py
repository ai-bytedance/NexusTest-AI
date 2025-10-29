from __future__ import annotations

import io
import json
import os
import subprocess
import zipfile
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.ai import clear_ai_provider_cache
from tests.test_projects import auth_headers, register_and_login


def _reset_provider_cache(monkeypatch: MonkeyPatch, provider_name: str) -> None:
    monkeypatch.setenv("PROVIDER", provider_name)
    get_settings.cache_clear()
    clear_ai_provider_cache()


def _create_project_and_api(client: TestClient, token: str) -> tuple[UUID, UUID]:
    project_response = client.post(
        "/api/v1/projects",
        json={"name": "AI Playground", "key": "aiplay", "description": ""},
        headers=auth_headers(token),
    )
    assert project_response.status_code == 200, project_response.text
    project_id = UUID(project_response.json()["data"]["id"])

    api_response = client.post(
        f"/api/v1/projects/{project_id}/apis",
        json={
            "name": "Demo API",
            "method": "GET",
            "path": "/demo",
            "version": "v1",
            "group_name": None,
            "headers": {},
            "params": {},
            "body": {},
            "mock_example": {"status": "ok", "value": 1},
        },
        headers=auth_headers(token),
    )
    assert api_response.status_code == 201, api_response.text
    api_id = UUID(api_response.json()["data"]["id"])
    return project_id, api_id


def test_ai_chat_generate_cases_save_and_export(
    client: TestClient,
    db_session: Session,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    _reset_provider_cache(monkeypatch, "mock")

    token = register_and_login(client, "ai-chat@example.com")
    project_id, api_id = _create_project_and_api(client, token)

    chat_request = {
        "project_id": str(project_id),
        "messages": [{"role": "user", "content": "请为该接口生成测试用例"}],
        "tools": ["generate_cases"],
        "context": {"api_id": str(api_id)},
    }

    chat_response = client.post(
        "/api/v1/ai/chat?provider=mock",
        json=chat_request,
        headers=auth_headers(token),
    )
    assert chat_response.status_code == 200, chat_response.text
    chat_payload = chat_response.json()["data"]
    chat_id = UUID(chat_payload["chat"]["id"])
    messages = chat_payload["messages"]
    assert len(messages) == 2

    assistant_message = messages[1]
    assert assistant_message["role"] == "assistant"
    assert assistant_message["content"]["kind"] == "cases"
    cases_from_ai = assistant_message["content"].get("cases") or []
    assert cases_from_ai, "AI should return generated test cases"

    save_response = client.post(
        f"/api/v1/ai/chats/{chat_id}/save-test-cases",
        json={
            "project_id": str(project_id),
            "message_id": assistant_message["id"],
            "api_id": str(api_id),
        },
        headers=auth_headers(token),
    )
    assert save_response.status_code == 201, save_response.text
    saved_payload = save_response.json()["data"]
    saved_cases = saved_payload["cases"]
    assert saved_cases, "Expected saved test cases"

    list_response = client.get(
        "/api/v1/ai/chats",
        params={"project_id": str(project_id)},
        headers=auth_headers(token),
    )
    assert list_response.status_code == 200, list_response.text
    chats_list = list_response.json()["data"]
    assert len(chats_list) == 1
    assert chats_list[0]["message_count"] >= 2

    detail_response = client.get(
        f"/api/v1/ai/chats/{chat_id}",
        params={"project_id": str(project_id)},
        headers=auth_headers(token),
    )
    assert detail_response.status_code == 200, detail_response.text
    detail_payload = detail_response.json()["data"]
    assert len(detail_payload["messages"]) == 2

    case_ids = [UUID(case["id"]) for case in saved_cases]
    export_response = client.post(
        "/api/v1/exports/pytest",
        json={"project_id": str(project_id), "case_ids": [str(case_id) for case_id in case_ids]},
        headers=auth_headers(token),
    )
    assert export_response.status_code == 200, export_response.text
    assert export_response.headers["content-type"] == "application/zip"

    archive_bytes = export_response.content
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        names = {name for name in archive.namelist()}
        assert "tests/conftest.py" in names
        assert any(name.startswith("tests/test_") and name.endswith(".py") for name in names)
        archive.extractall(tmp_path)

    env = os.environ.copy()
    env.setdefault("BASE_URL", "https://example.com")
    env.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    result = subprocess.run(
        ["pytest", "-q"],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(f"Exported pytest suite failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")

    _reset_provider_cache(monkeypatch, "mock")
