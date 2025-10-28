from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.services.importers import openapi_importer


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register_and_login(client: TestClient, email: str, password: str = "changeme123") -> str:
    register_response = client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    assert register_response.status_code == 201, register_response.text

    login_response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200, login_response.text
    data = login_response.json()["data"]
    return data["access_token"]


def test_project_crud_and_openapi_import(client: TestClient, monkeypatch: MonkeyPatch) -> None:
    admin_token = register_and_login(client, "admin@example.com")

    project_response = client.post(
        "/api/v1/projects",
        json={"name": "Demo Project", "key": "demo", "description": "Test"},
        headers=auth_headers(admin_token),
    )
    assert project_response.status_code == 200, project_response.text
    project_payload = project_response.json()["data"]
    project_id = project_payload["id"]

    list_response = client.get("/api/v1/projects", headers=auth_headers(admin_token))
    assert list_response.status_code == 200
    assert len(list_response.json()["data"]) == 1

    api_response = client.post(
        f"/api/v1/projects/{project_id}/apis",
        json={
            "name": "Ping",
            "method": "GET",
            "path": "/ping",
            "version": "v1",
            "group_name": "utilities",
            "headers": {},
            "params": {},
            "body": {},
            "mock_example": {},
        },
        headers=auth_headers(admin_token),
    )
    assert api_response.status_code == 201, api_response.text
    api_payload = api_response.json()["data"]
    assert api_payload["name"] == "Ping"

    def fake_fetch_openapi_spec(url: str, *, timeout: float = 15.0) -> dict[str, Any]:
        return {
            "openapi": "3.0.0",
            "info": {"title": "Service", "version": "v1"},
            "paths": {
                "/users": {
                    "post": {
                        "summary": "Create user",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "email": {"type": "string"},
                                        },
                                    }
                                }
                            }
                        },
                        "responses": {
                            "201": {
                                "description": "Created",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {"id": {"type": "string"}},
                                        },
                                        "example": {"id": "123"},
                                    }
                                },
                            }
                        },
                    }
                }
            },
        }

    monkeypatch.setattr(openapi_importer, "fetch_openapi_spec", fake_fetch_openapi_spec)

    import_response = client.post(
        f"/api/v1/projects/{project_id}/import/openapi",
        json={"url": "https://example.com/openapi.json"},
        headers=auth_headers(admin_token),
    )
    assert import_response.status_code == 200, import_response.text
    summary = import_response.json()["data"]["summary"]
    assert summary["created"] == 1

    apis_after_import = client.get(
        f"/api/v1/projects/{project_id}/apis",
        headers=auth_headers(admin_token),
    )
    assert apis_after_import.status_code == 200
    assert len(apis_after_import.json()["data"]) == 2

    member_token = register_and_login(client, "member@example.com")

    forbidden_response = client.get(
        f"/api/v1/projects/{project_id}",
        headers=auth_headers(member_token),
    )
    assert forbidden_response.status_code == 403

    add_member_response = client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"email": "member@example.com", "role": "member"},
        headers=auth_headers(admin_token),
    )
    assert add_member_response.status_code == 201, add_member_response.text

    member_projects = client.get("/api/v1/projects", headers=auth_headers(member_token))
    assert member_projects.status_code == 200
    assert len(member_projects.json()["data"]) == 1

    member_apis = client.get(
        f"/api/v1/projects/{project_id}/apis",
        headers=auth_headers(member_token),
    )
    assert member_apis.status_code == 200
    assert len(member_apis.json()["data"]) == 2
