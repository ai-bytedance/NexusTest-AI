from __future__ import annotations

from typing import Any

from app.services.ai.base import AIProvider, ProviderResponse, TokenUsage


class MockProvider(AIProvider):
    name = "mock"

    def __init__(self) -> None:
        super().__init__()
        self.model = "mock-model"

    def _wrap(self, payload: dict[str, Any]) -> ProviderResponse:
        usage = TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
        self._record_usage(usage)
        return ProviderResponse(payload=payload, model=self.model, usage=usage)

    def generate_test_cases(self, api_spec: dict[str, Any] | str) -> ProviderResponse:
        payload = {
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
        return self._wrap(payload)

    def generate_assertions(self, example_response: dict[str, Any] | str) -> ProviderResponse:
        payload = {
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
        return self._wrap(payload)

    def generate_mock_data(self, json_schema: dict[str, Any]) -> ProviderResponse:
        payload = {
            "data": {
                "id": "mock-123",
                "name": "Sample Item",
                "status": "active",
                "created_at": "2024-01-01T00:00:00Z",
                "metadata": {"source": "mock-provider", "version": 1},
            }
        }
        return self._wrap(payload)

    def summarize_report(self, report: dict[str, Any]) -> ProviderResponse:
        payload = {
            "markdown": (
                "## Test Execution Summary\n\n"
                "- ✅ Passed: 8\n"
                "- ❌ Failed: 2\n"
                "- ⏱️ Duration: 1m 23s\n\n"
                "Focus on stabilising the login endpoint assertions. Rerun once the "
                "validation fixes are deployed."
            )
        }
        return self._wrap(payload)


__all__ = ["MockProvider"]
