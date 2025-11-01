from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import importers as importers_routes
from app.models.api import Api
from app.models.import_source import ImportSource, ImportSourceType, ImporterKind
from app.services.importers import openapi_importer
from app.services.importers import resync as resync_service

FIXTURES = Path(__file__).parent / "fixtures"


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register_and_login(client: TestClient, email: str) -> str:
    register_resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": "changeme123"},
    )
    assert register_resp.status_code == 201, register_resp.text
    login_resp = client.post(
        "/api/auth/login",
        json={"email": email, "password": "changeme123"},
    )
    assert login_resp.status_code == 200, login_resp.text
    return login_resp.json()["data"]["access_token"]


def load_fixture(name: str) -> dict[str, Any]:
    with (FIXTURES / name).open() as handle:
        return json.load(handle)


def create_project(client: TestClient, token: str, name: str) -> str:
    response = client.post(
        "/api/v1/projects",
        json={"name": name, "key": name[:3].lower(), "description": ""},
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["id"]


def test_openapi_import_and_diff_preview(client: TestClient, db_session: Session) -> None:
    token = register_and_login(client, "owner@example.com")
    project_id = create_project(client, token, "Complex")

    spec = load_fixture("complex_openapi.json")

    import_resp = client.post(
        f"/api/v1/projects/{project_id}/import/openapi",
        json={"json": spec},
        headers=auth_headers(token),
    )
    assert import_resp.status_code == 200, import_resp.text
    summary = import_resp.json()["data"]["summary"]
    assert summary["created"] == 2
    assert summary["dry_run"] is False
    assert summary["run_id"] is not None
    assert summary["source_id"] is not None

    apis = db_session.execute(
        select(Api).where(Api.project_id == project_id, Api.is_deleted.is_(False))
    ).scalars().all()
    assert len(apis) == 2

    create_api = next(api for api in apis if api.method == "POST")
    assert create_api.normalized_path == "/users"
    assert create_api.headers["Authorization"] == "Bearer {{token}}"
    assert create_api.headers["trace-id"] == "abc-123"
    assert create_api.group_name == "users"
    assert create_api.metadata_["openapi"]["operation_vendor_extensions"]["x-operation-flag"] is True
    assert create_api.metadata_["openapi"]["selected_server"]["url"].startswith("https://api.example.com")
    assert "multipart/form-data" in create_api.body
    assert create_api.mock_example["responses"]["201"]["application/json"]["id"] == "user-1"

    get_api = next(api for api in apis if api.method == "GET")
    assert get_api.normalized_path == "/users/{userId}"
    assert get_api.params["verbose"] is True
    assert get_api.headers["X-API-Key"] == "{{apiKey}}"

    mutated_spec = deepcopy(spec)
    mutated_spec["paths"]["/users"]["post"]["parameters"][0]["example"] = "xyz-999"

    dry_run_resp = client.post(
        f"/api/v1/projects/{project_id}/import/openapi",
        json={"json": mutated_spec, "dry_run": True},
        headers=auth_headers(token),
    )
    assert dry_run_resp.status_code == 200, dry_run_resp.text
    dry_run_summary = dry_run_resp.json()["data"]["summary"]
    assert dry_run_summary["dry_run"] is True
    assert dry_run_summary["updated"] >= 1
    assert dry_run_summary["run_id"] is not None

    post_item = next(
        item
        for item in dry_run_summary["items"]
        if item["method"] == "POST" and item["normalized_path"] == "/users"
    )
    assert post_item["diff"]["headers"]["to"]["trace-id"] == "xyz-999"

    preview_resp = client.get(
        f"/api/v1/projects/{project_id}/import/preview",
        params={"id": dry_run_summary["run_id"]},
        headers=auth_headers(token),
    )
    assert preview_resp.status_code == 200, preview_resp.text
    preview_summary = preview_resp.json()["data"]["summary"]
    assert preview_summary["dry_run"] is True
    assert preview_summary["items"][0]["diff"]

    refreshed_api = db_session.get(Api, create_api.id)
    assert refreshed_api.headers["trace-id"] == "abc-123"


def test_openapi_resync_from_url(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = register_and_login(client, "syncer@example.com")
    project_id = create_project(client, token, "SyncProj")

    spec_state = {"payload": load_fixture("complex_openapi.json")}

    def fake_fetch(url: str, *, timeout: float = 15.0) -> tuple[dict[str, Any], str]:
        return deepcopy(spec_state["payload"]), url

    monkeypatch.setattr(importers_routes, "fetch_openapi_spec", fake_fetch)
    monkeypatch.setattr(openapi_importer, "fetch_openapi_spec", fake_fetch)
    monkeypatch.setattr(resync_service, "fetch_openapi_spec", fake_fetch)

    initial_resp = client.post(
        f"/api/v1/projects/{project_id}/import/openapi",
        json={"url": "https://example.com/openapi.json"},
        headers=auth_headers(token),
    )
    assert initial_resp.status_code == 200, initial_resp.text
    initial_summary = initial_resp.json()["data"]["summary"]
    source_id = initial_summary["source_id"]

    apis_before = db_session.execute(
        select(Api).where(Api.project_id == project_id, Api.is_deleted.is_(False))
    ).scalars().all()
    assert len(apis_before) == 2

    mutated = deepcopy(spec_state["payload"])
    mutated["paths"]["/users"]["post"]["parameters"][0]["example"] = "delta-555"
    spec_state["payload"] = mutated

    dry_run_resync = client.post(
        f"/api/v1/projects/{project_id}/import/resync",
        json={"source_id": source_id, "dry_run": True},
        headers=auth_headers(token),
    )
    assert dry_run_resync.status_code == 200, dry_run_resync.text
    resync_summary = dry_run_resync.json()["data"]["summary"]
    assert resync_summary["dry_run"] is True
    assert resync_summary["updated"] >= 1

    apply_resync = client.post(
        f"/api/v1/projects/{project_id}/import/resync",
        json={"source_id": source_id},
        headers=auth_headers(token),
    )
    assert apply_resync.status_code == 200, apply_resync.text
    apply_summary = apply_resync.json()["data"]["summary"]
    assert apply_summary["dry_run"] is False

    updated_api = db_session.execute(
        select(Api).where(
            Api.project_id == project_id,
            Api.method == "POST",
            Api.normalized_path == "/users",
            Api.is_deleted.is_(False),
        )
    ).scalar_one()
    assert updated_api.headers["trace-id"] == "delta-555"


def test_postman_import_variables_and_auth(client: TestClient, db_session: Session) -> None:
    token = register_and_login(client, "postman@example.com")
    project_id = create_project(client, token, "PostmanProj")

    collection = load_fixture("postman_collection.json")
    options = {
        "environment": {
            "userId": "42",
            "includeFlag": "full",
            "envToken": "abc123",
            "correlationId": "corr-9"
        },
        "globals": {"baseUrl": "https://api.test.local"},
        "resolve_variables": True,
        "inherit_auth": True,
    }

    import_resp = client.post(
        f"/api/v1/projects/{project_id}/import/postman",
        json={"collection": collection, "options": options},
        headers=auth_headers(token),
    )
    assert import_resp.status_code == 200, import_resp.text
    summary = import_resp.json()["data"]["summary"]
    assert summary["created"] == 2
    assert summary["dry_run"] is False

    apis = db_session.execute(
        select(Api).where(Api.project_id == project_id, Api.is_deleted.is_(False))
    ).scalars().all()
    assert len(apis) == 2

    get_api = next(api for api in apis if api.method == "GET")
    assert get_api.normalized_path == "/users/{userId}"
    assert get_api.params["include"] == "full"
    assert get_api.headers["Authorization"] == "Bearer abc123"
    assert get_api.headers["X-Correlation-Id"] == "corr-9"
    assert get_api.metadata_["postman"]["folder_path"] == ["User APIs"]
    assert "pm.variables.set" in get_api.metadata_["postman"]["pre_request_script"]
    assert get_api.metadata_["postman"]["resolved_url"] == "https://api.test.local/users/42?include=full"

    post_api = next(api for api in apis if api.method == "POST")
    assert post_api.group_name == "User APIs"
    assert post_api.body["formdata"]["name"] == "Ada"
    assert post_api.body["files"]["avatar"] == ["./avatar.png"]
    assert post_api.metadata_["postman"]["auth"]["type"] == "bearer"

    source = db_session.execute(
        select(ImportSource).where(
            ImportSource.project_id == project_id,
            ImportSource.importer == ImporterKind.POSTMAN,
            ImportSource.is_deleted.is_(False),
        )
    ).scalar_one()
    assert source.source_type == ImportSourceType.RAW
    assert source.location.startswith("raw:")
