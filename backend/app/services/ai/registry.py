from __future__ import annotations

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
        base_url=(settings.deepseek_base_url or "https://api.deepseek.com"),
        model=getattr(settings, "deepseek_model", "deepseek-chat"),
        timeout=float(settings.request_timeout_seconds),
    )


def _build_openai(settings: Settings) -> AIProvider:
    if not settings.openai_api_key:
        _logger.warning("ai_provider_missing_credentials", provider="openai", fallback="mock")
        return MockProvider()
    return OpenAIProvider(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        base_url=settings.openai_base_url,
        timeout=float(settings.request_timeout_seconds),
    )


def _build_anthropic(settings: Settings) -> AIProvider:
    if not settings.anthropic_api_key:
        _logger.warning("ai_provider_missing_credentials", provider="anthropic", fallback="mock")
        return MockProvider()
    return ClaudeProvider(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
        base_url=settings.anthropic_base_url,
        timeout=float(settings.request_timeout_seconds),
    )


def _build_gemini(settings: Settings) -> AIProvider:
    if not settings.google_api_key:
        _logger.warning("ai_provider_missing_credentials", provider="gemini", fallback="mock")
        return MockProvider()
    return GeminiProvider(
        api_key=settings.google_api_key,
        model=settings.gemini_model,
        base_url=settings.google_base_url,
        timeout=float(settings.request_timeout_seconds),
    )


def _build_qwen(settings: Settings) -> AIProvider:
    if not settings.qwen_api_key:
        _logger.warning("ai_provider_missing_credentials", provider="qwen", fallback="mock")
        return MockProvider()
    return QwenProvider(
        api_key=settings.qwen_api_key,
        model=settings.qwen_model,
        base_url=settings.qwen_base_url,
        timeout=float(settings.request_timeout_seconds),
    )


def _build_glm(settings: Settings) -> AIProvider:
    if not settings.zhipu_api_key:
        _logger.warning("ai_provider_missing_credentials", provider="glm", fallback="mock")
        return MockProvider()
    return GLMProvider(
        api_key=settings.zhipu_api_key,
        model=settings.glm_model,
        base_url=settings.zhipu_base_url,
        timeout=float(settings.request_timeout_seconds),
    )


def _build_doubao(settings: Settings) -> AIProvider:
    if not settings.doubao_api_key:
        _logger.warning("ai_provider_missing_credentials", provider="doubao", fallback="mock")
        return MockProvider()
    return DoubaoProvider(
        api_key=settings.doubao_api_key,
        model=settings.doubao_model,
        base_url=settings.doubao_base_url,
        timeout=float(settings.request_timeout_seconds),
    )


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


_PROVIDER_CACHE: dict[str, AIProvider] = {}


def get_ai_provider(provider_override: str | None = None) -> AIProvider:
    settings = get_settings()
    configured = provider_override or settings.provider or "mock"
    provider_key = configured.strip().lower() or "mock"
    builder = _PROVIDER_BUILDERS.get(provider_key)
    if builder is None:
        _logger.warning("ai_provider_unknown", configured=configured, fallback="mock")
        provider_key = "mock"
        builder = _PROVIDER_BUILDERS["mock"]

    provider = _PROVIDER_CACHE.get(provider_key)
    if provider is None:
        provider = builder(settings)
        _PROVIDER_CACHE[provider_key] = provider
        _logger.info(
            "ai_provider_initialized",
            configured=configured,
            resolved=provider.provider_name,
        )
    return provider


def clear_ai_provider_cache() -> None:
    _PROVIDER_CACHE.clear()


__all__ = ["get_ai_provider", "clear_ai_provider_cache"]
