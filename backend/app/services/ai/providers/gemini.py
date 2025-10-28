from __future__ import annotations

from typing import Any

from app.services.ai.base import AIProvider, AIProviderNotImplementedError


class GeminiProvider(AIProvider):
    name = "gemini"

    def _raise(self) -> None:
        raise AIProviderNotImplementedError(
            "Google Gemini provider is not implemented yet. Switch to PROVIDER=mock or supply an implementation."
        )

    def generate_test_cases(self, api_spec: dict[str, Any] | str) -> dict[str, Any]:
        self._raise()

    def generate_assertions(self, example_response: dict[str, Any] | str) -> dict[str, Any]:
        self._raise()

    def generate_mock_data(self, json_schema: dict[str, Any]) -> dict[str, Any]:
        self._raise()

    def summarize_report(self, report: dict[str, Any]) -> str:
        self._raise()


__all__ = ["GeminiProvider"]
