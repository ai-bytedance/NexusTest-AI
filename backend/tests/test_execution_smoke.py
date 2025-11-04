from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.tasks import celery_app


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register_and_login(client: TestClient, email: str, password: str = "changeme123") -> str:
    register_response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert register_response.status_code == 201, register_response.text

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200, login_response.text
    return login_response.json()["data"]["access_token"]


def _mock_http_request(method: str, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
    request = httpx.Request(method, url)
    if url.endswith("/case"):
        payload = {"status": "ok", "value": 123}
    elif url.endswith("/first"):
        payload = {"value": "first"}
    elif url.endswith("/second"):
        prev_value = (params or {}).get("from_prev")
        payload = {"value": f"second-{prev_value}"}
    else:
        payload = {"status": "unknown"}
    return httpx.Response(200, json=payload, request=request)


def test_case_and_suite_execution_flow(client: TestClient, monkeypatch: MonkeyPatch) -> None:
    original_always_eager = celery_app.conf.task_always_eager
    original_eager_propagates = celery_app.conf.task_eager_propagates
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    def fake_request(self: httpx.Client, method: str, url: str, **kwargs: Any) -> httpx.Response:
        params = kwargs.get("params")
        if isinstance(params, httpx.QueryParams):
            params = dict(params)
        return _mock_http_request(method, url, params=params)

    monkeypatch.setattr(httpx.Client, "request", fake_request, raising=False)

    try:
        token = register_and_login(client, "runner@example.com")

        project = client.post(
            "/api/v1/projects",
            json={"name": "Runner", "key": "run", "description": ""},
            headers=auth_headers(token),
        )
        assert project.status_code == 200, project.text
        project_payload = project.json()["data"]
        project_id: UUID = UUID(project_payload["id"])

        api_response = client.post(
            f"/api/v1/projects/{project_id}/apis",
            json={
                "name": "Case API",
                "method": "GET",
                "path": "/case",
                "version": "v1",
                "group_name": None,
                "headers": {},
                "params": {},
                "body": {},
                "mock_example": {},
            },
            headers=auth_headers(token),
        )
        assert api_response.status_code == 201, api_response.text
        api_id = api_response.json()["data"]["id"]

        case_response = client.post(
            f"/api/v1/projects/{project_id}/test-cases",
            json={
                "name": "Smoke Case",
                "api_id": api_id,
                "inputs": {"method": "GET", "url": "https://example.com/case"},
                "expected": {},
                "assertions": [
                    {"operator": "status_code", "expected": 200},
                    {"operator": "jsonpath_equals", "path": "$.status", "expected": "ok"},
                ],
                "enabled": True,
            },
            headers=auth_headers(token),
        )
        assert case_response.status_code == 201, case_response.text
        case_id = case_response.json()["data"]["id"]

        trigger_case = client.post(
            f"/api/v1/projects/{project_id}/execute/case/{case_id}",
            headers=auth_headers(token),
        )
        assert trigger_case.status_code == 202, trigger_case.text
        case_task_data = trigger_case.json()["data"]
        case_report_id = case_task_data["report_id"]
        case_task_id = case_task_data["task_id"]

        report_response = client.get(
            f"/api/v1/reports/{case_report_id}",
            headers=auth_headers(token),
        )
        assert report_response.status_code == 200, report_response.text
        assert report_response.json()["data"]["status"] == "passed"

        task_status = client.get(
            f"/api/v1/tasks/{case_task_id}",
            headers=auth_headers(token),
        )
        assert task_status.status_code == 200
        payload = task_status.json()["data"]
        assert payload["report_id"] == case_report_id
        assert payload["report_url"] == f"/reports/{case_report_id}"

        suite_response = client.post(
            f"/api/v1/projects/{project_id}/test-suites",
            json={
                "name": "Smoke Suite",
                "description": None,
                "steps": [
                    {
                        "alias": "first",
                        "inputs": {
                            "method": "GET",
                            "url": "{{variables.base_url}}/first",
                        },
                        "assertions": [
                            {"operator": "status_code", "expected": 200},
                            {"operator": "jsonpath_equals", "path": "$.value", "expected": "first"},
                        ],
                    },
                    {
                        "alias": "second",
                        "inputs": {
                            "method": "GET",
                            "url": "{{variables.base_url}}/second",
                            "params": {"from_prev": "{{prev.first.jsonpath('$.value')}}"},
                        },
                        "assertions": [
                            {"operator": "status_code", "expected": 200},
                            {
                                "operator": "contains",
                                "actual": "{{response.jsonpath('$.value')}}",
                                "expected": "second",
                            },
                            {"operator": "equals", "actual": "{{prev.first.jsonpath('$.value')}}", "expected": "first"},
                        ],
                    },
                ],
                "variables": {"base_url": "https://example.com"},
            },
            headers=auth_headers(token),
        )
        assert suite_response.status_code == 201, suite_response.text
        suite_id = suite_response.json()["data"]["id"]

        trigger_suite = client.post(
            f"/api/v1/projects/{project_id}/execute/suite/{suite_id}",
            headers=auth_headers(token),
        )
        assert trigger_suite.status_code == 202, trigger_suite.text
        suite_task_data = trigger_suite.json()["data"]
        suite_report_id = suite_task_data["report_id"]

        suite_report = client.get(
            f"/api/v1/reports/{suite_report_id}",
            headers=auth_headers(token),
        )
        assert suite_report.status_code == 200, suite_report.text
        suite_payload = suite_report.json()["data"]
        assert suite_payload["status"] == "passed"
        assert suite_payload["assertions_result"]["passed"] is True
        assert len(suite_payload["assertions_result"]["steps"]) == 2
    finally:
        celery_app.conf.task_always_eager = original_always_eager
        celery_app.conf.task_eager_propagates = original_eager_propagates
