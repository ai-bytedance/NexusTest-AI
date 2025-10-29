from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from fastapi import status

from app.core.errors import ErrorCode


@dataclass
class TokenUsage:
    """Token accounting for a single provider invocation."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            prompt_tokens=self._merge_component(self.prompt_tokens, other.prompt_tokens),
            completion_tokens=self._merge_component(self.completion_tokens, other.completion_tokens),
            total_tokens=self._merge_component(self.total_tokens, other.total_tokens),
        )

    def as_dict(self) -> dict[str, int]:
        payload: dict[str, int] = {}
        if self.prompt_tokens is not None:
            payload["prompt_tokens"] = self.prompt_tokens
        if self.completion_tokens is not None:
            payload["completion_tokens"] = self.completion_tokens
        if self.total_tokens is not None:
            payload["total_tokens"] = self.total_tokens
        return payload

    @staticmethod
    def _merge_component(first: int | None, second: int | None) -> int | None:
        if first is None and second is None:
            return None
        first_value = 0 if first is None else first
        second_value = 0 if second is None else second
        return first_value + second_value

    @staticmethod
    def _coerce(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool):  # guard against bools being ints
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str) and value.strip():
            try:
                return int(float(value.strip()))
            except ValueError:
                return None
        return None

    @classmethod
    def from_raw(cls, raw: Any) -> "TokenUsage" | None:
        if raw is None:
            return None
        if isinstance(raw, TokenUsage):
            return raw
        if not isinstance(raw, dict):
            return None

        prompt = cls._coerce(
            raw.get("prompt_tokens")
            or raw.get("input_tokens")
            or raw.get("promptTokens")
            or raw.get("prompt_token_count")
            or raw.get("promptTokenCount")
        )
        completion = cls._coerce(
            raw.get("completion_tokens")
            or raw.get("output_tokens")
            or raw.get("completionTokens")
            or raw.get("candidates_token_count")
            or raw.get("candidatesTokenCount")
            or raw.get("completionTokenCount")
        )
        total = cls._coerce(
            raw.get("total_tokens")
            or raw.get("total_token_count")
            or raw.get("totalTokenCount")
        )
        if total is None and prompt is not None and completion is not None:
            total = prompt + completion
        return cls(prompt_tokens=prompt, completion_tokens=completion, total_tokens=total)


@dataclass
class ProviderResponse:
    """Represents the structured response returned by a provider call."""

    payload: dict[str, Any]
    model: str | None = None
    usage: TokenUsage | None = None


_JSON_OBJECT_RE = re.compile(r"\{.*?\}", re.DOTALL)


def extract_json_object(candidate: str) -> dict[str, Any]:
    """Extract the first JSON object found within a text block."""

    text = candidate.strip()
    if not text:
        raise ValueError("Empty content received from provider")

    if text.startswith("```"):
        # Handle fenced code blocks such as ```json ... ```
        segments = [segment.strip() for segment in text.split("```") if segment.strip()]
        for segment in segments:
            if segment.startswith("{"):
                text = segment
                break

    attempts = [text]
    attempts.extend(match.group(0).strip() for match in _JSON_OBJECT_RE.finditer(text))

    for attempt in attempts:
        if not attempt:
            continue
        try:
            parsed = json.loads(attempt)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("No JSON object could be parsed from provider response")


class AIProviderError(Exception):
    """Base exception for AI provider failures."""

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.AI_PROVIDER_ERROR,
        status_code: int = status.HTTP_502_BAD_GATEWAY,
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.data = data


class AIProviderRateLimitError(AIProviderError):
    def __init__(self, message: str, *, data: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code=ErrorCode.AI_PROVIDER_RATE_LIMIT,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            data=data,
        )


class AIProviderTimeoutError(AIProviderError):
    def __init__(self, message: str, *, data: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code=ErrorCode.AI_PROVIDER_TIMEOUT,
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            data=data,
        )


class AIProviderUnavailableError(AIProviderError):
    def __init__(self, message: str, *, data: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code=ErrorCode.AI_PROVIDER_UNAVAILABLE,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            data=data,
        )


class AIProviderNotConfiguredError(AIProviderError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            code=ErrorCode.AI_PROVIDER_NOT_CONFIGURED,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class AIProviderNotImplementedError(AIProviderError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            code=ErrorCode.AI_PROVIDER_NOT_IMPLEMENTED,
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
        )


class AIProvider(ABC):
    name: str = "provider"

    def __init__(self) -> None:
        self._usage_totals = TokenUsage()

    def __repr__(self) -> str:  # pragma: no cover - convenience only
        return f"{self.__class__.__name__}(name='{self.name}')"

    @property
    def provider_name(self) -> str:
        return self.name

    def _record_usage(self, usage: TokenUsage | None) -> TokenUsage | None:
        if usage is None:
            return None
        if self._usage_totals is None:
            self._usage_totals = usage
        else:
            self._usage_totals = self._usage_totals + usage
        return usage

    @property
    def usage_totals(self) -> TokenUsage:
        return self._usage_totals

    @abstractmethod
    def generate_test_cases(self, api_spec: dict[str, Any] | str) -> ProviderResponse:
        raise NotImplementedError

    @abstractmethod
    def generate_assertions(self, example_response: dict[str, Any] | str) -> ProviderResponse:
        raise NotImplementedError

    @abstractmethod
    def generate_mock_data(self, json_schema: dict[str, Any]) -> ProviderResponse:
        raise NotImplementedError

    @abstractmethod
    def summarize_report(self, report: dict[str, Any]) -> ProviderResponse:
        raise NotImplementedError


__all__ = [
    "AIProvider",
    "AIProviderError",
    "AIProviderRateLimitError",
    "AIProviderTimeoutError",
    "AIProviderUnavailableError",
    "AIProviderNotConfiguredError",
    "AIProviderNotImplementedError",
    "TokenUsage",
    "ProviderResponse",
    "extract_json_object",
]
