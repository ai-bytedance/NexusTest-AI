from __future__ import annotations

from typing import Any

from app.services.ai.base import AIProvider


class MockProvider(AIProvider):
    name = "mock"

    def generate_test_cases(self, api_spec: dict[str, Any] | str) -> dict[str, Any]:
        return {
            "cases": [
                {
                    "name": "Happy path returns 200",
                    "description": "Send a request and expect a successful 200 response.",
                    "steps": [
                        {"action": "prepare_request", "note": "Use default headers and payload"},
                        {"action": "send_request", "method": "GET", "path": "/demo"},
                    ],
                    "assertions": [
                        {"name": "status_ok", "operator": "status_code", "expected": 200},
                        {
                            "name": "response_success_flag",
                            "operator": "jsonpath_equals",
                            "path": "$.success",
                            "expected": True,
                        },
                    ],
                },
                {
                    "name": "Validation error on bad payload",
                    "description": "Submit an invalid payload and expect a 400 validation error.",
                    "steps": [
                        {"action": "prepare_request", "payload": {"invalid": True}},
                        {"action": "send_request", "method": "POST", "path": "/demo"},
                    ],
                    "assertions": [
                        {"name": "status_bad_request", "operator": "status_code", "expected": 400},
                        {
                            "name": "error_code_matches",
                            "operator": "jsonpath_equals",
                            "path": "$.error.code",
                            "expected": "VALIDATION_ERROR",
                        },
                    ],
                },
            ]
        }

    def generate_assertions(self, example_response: dict[str, Any] | str) -> dict[str, Any]:
        return {
            "assertions": [
                {"name": "status_ok", "operator": "status_code", "expected": 200},
                {
                    "name": "content_type_json",
                    "operator": "equals",
                    "actual": "{{ response.headers.Content-Type }}",
                    "expected": "application/json",
                },
                {
                    "name": "payload_not_empty",
                    "operator": "not_equals",
                    "actual": "{{ response.json.data }}",
                    "expected": {},
                },
            ]
        }

    def generate_mock_data(self, json_schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "data": {
                "id": "mock-123",
                "name": "Sample Item",
                "status": "active",
                "created_at": "2024-01-01T00:00:00Z",
                "metadata": {"source": "mock-provider", "version": 1},
            }
        }

    def summarize_report(self, report: dict[str, Any]) -> str:
        return (
            "## Test Execution Summary\n\n"
            "- ✅ Passed: 8\n"
            "- ❌ Failed: 2\n"
            "- ⏱️ Duration: 1m 23s\n\n"
            "Focus on stabilising the login endpoint assertions. Rerun once the "
            "validation fixes are deployed."
        )


__all__ = ["MockProvider"]
