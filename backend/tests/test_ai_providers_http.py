from __future__ import annotations

import json
from typing import Any, Iterable

import httpx
import pytest

from app.services.ai.base import (
    AIProviderRateLimitError,
    AIProviderUnavailableError,
)
from app.services.ai.providers.anthropic import ClaudeProvider
from app.services.ai.providers.doubao import DoubaoProvider
from app.services.ai.providers.gemini import GeminiProvider
from app.services.ai.providers.glm import GLMProvider
from app.services.ai.providers.openai import OpenAIProvider
from app.services.ai.providers.qwen import QwenProvider
from app.services.ai.providers.deepseek import DeepSeekProvider


CASES_PAYLOAD = {
    "cases": [
        {
            "name": "List users returns 200",
            "description": "Validate success response",
            "steps": [
                {"action": "send_request", "method": "GET", "path": "/users"},
            ],
            "assertions": [
                {"name": "status_code", "operator": "status_code", "expected": 200},
            ],
        }
    ]
}
CASES_TEXT = json.dumps(CASES_PAYLOAD)


def _response(payload: dict[str, Any], *, status_code: int = 200, url: str = "https://api.test") -> httpx.Response:
    request = httpx.Request("POST", url)
    return httpx.Response(status_code=status_code, json=payload, request=request)


def _install_httpx_mock(monkeypatch: pytest.MonkeyPatch, responses: Iterable[Any], module_path: str) -> list[dict[str, Any]]:
    responses_iter = iter(responses)
    calls: list[dict[str, Any]] = []

    class _FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401 - signature compatibility
            pass

        def post(self, url: str, *, headers: dict[str, Any] | None = None, json: Any = None, params: Any = None) -> httpx.Response:
            calls.append({"url": url, "headers": headers or {}, "json": json, "params": params})
            try:
                outcome = next(responses_iter)
            except StopIteration as exc:  # pragma: no cover - guardrail for misconfigured tests
                raise AssertionError("No more fake responses configured") from exc
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        def __enter__(self) -> "_FakeClient":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

    monkeypatch.setattr(httpx, "Client", lambda *args, **kwargs: _FakeClient())
    monkeypatch.setattr(f"{module_path}.time.sleep", lambda *args, **kwargs: None)
    return calls


def test_openai_provider_responses_success(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _response(
            {
                "id": "resp_123",
                "model": "gpt-4o-mini",
                "usage": {"prompt_tokens": 12, "completion_tokens": 18, "total_tokens": 30},
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": CASES_TEXT},
                        ],
                    }
                ],
            }
        )
    ]
    _install_httpx_mock(monkeypatch, responses, "app.services.ai.providers.openai")

    provider = OpenAIProvider(api_key="test-key", model="gpt-4o-mini")
    result = provider.generate_test_cases({"path": "/users"})

    assert result.payload == CASES_PAYLOAD
    assert result.model == "gpt-4o-mini"
    assert result.usage and result.usage.total_tokens == 30
    assert provider.usage_totals.total_tokens == 30


def test_openai_provider_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    rate_limited = _response({"error": {"message": "limited"}}, status_code=429)
    responses = [rate_limited, rate_limited, rate_limited]
    _install_httpx_mock(monkeypatch, responses, "app.services.ai.providers.openai")

    provider = OpenAIProvider(api_key="test-key", model="gpt-4o-mini", max_retries=3)

    with pytest.raises(AIProviderRateLimitError):
        provider.generate_test_cases({"path": "/users"})


def test_anthropic_provider_success(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _response(
            {
                "model": "claude-3-5-sonnet-20240620",
                "usage": {"input_tokens": 10, "output_tokens": 20},
                "content": [
                    {"type": "text", "text": CASES_TEXT},
                ],
            }
        )
    ]
    _install_httpx_mock(monkeypatch, responses, "app.services.ai.providers.anthropic")

    provider = ClaudeProvider(api_key="test", model="claude-3-5-sonnet-20240620")
    result = provider.generate_test_cases({"path": "/users"})

    assert result.payload["cases"][0]["name"] == CASES_PAYLOAD["cases"][0]["name"]
    assert result.model == "claude-3-5-sonnet-20240620"
    assert result.usage and result.usage.prompt_tokens == 10


def test_gemini_provider_success(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _response(
            {
                "modelVersion": "gemini-1.5-flash",
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": CASES_TEXT}],
                        }
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 14,
                    "candidatesTokenCount": 21,
                    "totalTokenCount": 35,
                },
            }
        )
    ]
    _install_httpx_mock(monkeypatch, responses, "app.services.ai.providers.gemini")

    provider = GeminiProvider(api_key="test", model="gemini-1.5-flash")
    result = provider.generate_test_cases({"path": "/users"})

    assert result.payload == CASES_PAYLOAD
    assert result.model == "gemini-1.5-flash"
    assert result.usage and result.usage.total_tokens == 35


def test_gemini_provider_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _response({}, status_code=500),
        _response({}, status_code=500),
        _response({}, status_code=500),
    ]
    _install_httpx_mock(monkeypatch, responses, "app.services.ai.providers.gemini")

    provider = GeminiProvider(api_key="test", model="gemini-1.5-flash", max_retries=3)

    with pytest.raises(AIProviderUnavailableError):
        provider.generate_test_cases({"path": "/users"})


def test_qwen_provider_success(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _response(
            {
                "model": "qwen-plus",
                "output": {"text": CASES_TEXT},
                "usage": {"input_tokens": 9, "output_tokens": 11, "total_tokens": 20},
                "code": 200,
            }
        )
    ]
    _install_httpx_mock(monkeypatch, responses, "app.services.ai.providers.qwen")

    provider = QwenProvider(api_key="test", model="qwen-plus")
    result = provider.generate_test_cases({"path": "/users"})

    assert result.payload == CASES_PAYLOAD
    assert result.usage and result.usage.total_tokens == 20


def test_glm_provider_success(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _response(
            {
                "model": "glm-4-airx",
                "choices": [
                    {"message": {"content": CASES_TEXT}},
                ],
                "usage": {"prompt_tokens": 8, "completion_tokens": 12, "total_tokens": 20},
            }
        )
    ]
    _install_httpx_mock(monkeypatch, responses, "app.services.ai.providers.glm")

    provider = GLMProvider(api_key="test", model="glm-4-airx")
    result = provider.generate_test_cases({"path": "/users"})

    assert result.payload == CASES_PAYLOAD
    assert result.model == "glm-4-airx"
    assert result.usage and result.usage.total_tokens == 20


def test_doubao_provider_success(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _response(
            {
                "model": "doubao-pro-4k",
                "choices": [
                    {"message": {"content": CASES_TEXT}},
                ],
                "usage": {"prompt_tokens": 6, "completion_tokens": 10, "total_tokens": 16},
            }
        )
    ]
    _install_httpx_mock(monkeypatch, responses, "app.services.ai.providers.doubao")

    provider = DoubaoProvider(api_key="test", model="doubao-pro-4k")
    result = provider.generate_test_cases({"path": "/users"})

    assert result.payload == CASES_PAYLOAD
    assert result.usage and result.usage.total_tokens == 16


def test_deepseek_provider_success(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _response(
            {
                "model": "deepseek-chat",
                "choices": [
                    {
                        "message": {
                            "content": CASES_TEXT,
                        }
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
            }
        )
    ]
    _install_httpx_mock(monkeypatch, responses, "app.services.ai.providers.deepseek")

    provider = DeepSeekProvider(api_key="test", model="deepseek-chat")
    result = provider.generate_test_cases({"path": "/users"})

    assert result.payload == CASES_PAYLOAD
    assert result.usage and result.usage.total_tokens == 12
