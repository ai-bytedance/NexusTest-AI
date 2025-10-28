from __future__ import annotations

from functools import lru_cache
from typing import Callable

from app.core.config import Settings, get_settings
from app.logging import get_logger
from app.services.ai.base import AIProvider
from app.services.ai.providers import (
    ClaudeProvider,
    DeepSeekProvider,
    DoubaoProvider,
    GeminiProvider,
    GLMProvider,
    MockProvider,
    OpenAIProvider,
    QwenProvider,
)

_logger = get_logger().bind(component="ai_provider_registry")


def _build_deepseek(settings: Settings) -> AIProvider:
    if not settings.deepseek_api_key:
        _logger.warning("ai_provider_missing_credentials", provider="deepseek", fallback="mock")
        return MockProvider()
    return DeepSeekProvider(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url or "https://api.deepseek.com",
        timeout=float(settings.request_timeout_seconds),
    )


def _build_openai(settings: Settings) -> AIProvider:
    if not settings.openai_api_key:
        _logger.warning("ai_provider_missing_credentials", provider="openai", fallback="mock")
        return MockProvider()
    return OpenAIProvider()


def _build_anthropic(settings: Settings) -> AIProvider:
    if not settings.anthropic_api_key:
        _logger.warning("ai_provider_missing_credentials", provider="anthropic", fallback="mock")
        return MockProvider()
    return ClaudeProvider()


def _build_gemini(settings: Settings) -> AIProvider:
    if not settings.google_api_key:
        _logger.warning("ai_provider_missing_credentials", provider="gemini", fallback="mock")
        return MockProvider()
    return GeminiProvider()


def _build_qwen(settings: Settings) -> AIProvider:
    if not settings.qwen_api_key:
        _logger.warning("ai_provider_missing_credentials", provider="qwen", fallback="mock")
        return MockProvider()
    return QwenProvider()


def _build_glm(settings: Settings) -> AIProvider:
    if not settings.zhipu_api_key:
        _logger.warning("ai_provider_missing_credentials", provider="glm", fallback="mock")
        return MockProvider()
    return GLMProvider()


def _build_doubao(settings: Settings) -> AIProvider:
    if not settings.doubao_api_key:
        _logger.warning("ai_provider_missing_credentials", provider="doubao", fallback="mock")
        return MockProvider()
    return DoubaoProvider()


_PROVIDER_BUILDERS: dict[str, Callable[[Settings], AIProvider]] = {
    "deepseek": _build_deepseek,
    "openai": _build_openai,
    "anthropic": _build_anthropic,
    "claude": _build_anthropic,
    "gemini": _build_gemini,
    "google": _build_gemini,
    "qwen": _build_qwen,
    "glm": _build_glm,
    "zhipu": _build_glm,
    "doubao": _build_doubao,
    "mock": lambda _settings: MockProvider(),
}


@lru_cache(maxsize=1)
def get_ai_provider() -> AIProvider:
    settings = get_settings()
    provider_key = (settings.provider or "mock").strip().lower()
    builder = _PROVIDER_BUILDERS.get(provider_key)
    if builder is None:
        _logger.warning("ai_provider_unknown", configured=settings.provider, fallback="mock")
        return MockProvider()

    provider = builder(settings)
    _logger.info("ai_provider_selected", configured=settings.provider, resolved=provider.provider_name)
    return provider


__all__ = ["get_ai_provider"]
