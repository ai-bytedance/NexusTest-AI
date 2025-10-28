from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from fastapi import status

from app.core.errors import ErrorCode


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

    def __repr__(self) -> str:  # pragma: no cover - convenience only
        return f"{self.__class__.__name__}(name='{self.name}')"

    @property
    def provider_name(self) -> str:
        return self.name

    @abstractmethod
    def generate_test_cases(self, api_spec: dict[str, Any] | str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def generate_assertions(self, example_response: dict[str, Any] | str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def generate_mock_data(self, json_schema: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def summarize_report(self, report: dict[str, Any]) -> str:
        raise NotImplementedError


__all__ = [
    "AIProvider",
    "AIProviderError",
    "AIProviderRateLimitError",
    "AIProviderTimeoutError",
    "AIProviderUnavailableError",
    "AIProviderNotConfiguredError",
    "AIProviderNotImplementedError",
]
