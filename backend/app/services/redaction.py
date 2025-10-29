from __future__ import annotations

import re
from typing import Any, Iterable

from app.core.config import get_settings

_SECRET_TEMPLATE_PATTERN = re.compile(r"{{\s*secret\.[^{}]+}}", re.IGNORECASE)
_TOKEN_PATTERN = re.compile(r"(?i)(?:api|secret|token|key)[^\s=:\-]{0,8}[:=\s]+([A-Za-z0-9._\-]{8,})")
_LONG_HEX_PATTERN = re.compile(r"\b[0-9a-f]{32,}\b", re.IGNORECASE)
_SK_PATTERN = re.compile(r"sk-[A-Za-z0-9]{12,}")


def sanitize_for_storage(
    value: Any,
    *,
    redact_fields: Iterable[str] | None = None,
    placeholder: str | None = None,
) -> Any:
    """Redact sensitive content prior to persistence or logging."""

    settings = get_settings()
    active_placeholder = placeholder or settings.redaction_placeholder or "***"
    redact_set = {item.lower() for item in (redact_fields or settings.redact_fields or [])}
    return _sanitize(value, redact_set, active_placeholder)


def _sanitize(data: Any, redact_keys: set[str], placeholder: str) -> Any:
    if data is None:
        return None
    if isinstance(data, dict):
        result: dict[str, Any] = {}
        for key, item in data.items():
            if isinstance(key, str) and key.lower() in redact_keys:
                result[key] = placeholder
            else:
                result[key] = _sanitize(item, redact_keys, placeholder)
        return result
    if isinstance(data, list):
        return [_sanitize(item, redact_keys, placeholder) for item in data]
    if isinstance(data, tuple):  # pragma: no cover - defensive
        return [_sanitize(item, redact_keys, placeholder) for item in data]
    if isinstance(data, set):  # pragma: no cover - defensive
        return [_sanitize(item, redact_keys, placeholder) for item in data]
    if isinstance(data, (bytes, bytearray)):
        decoded = bytes(data).decode("utf-8", errors="replace")
        return _sanitize(decoded, redact_keys, placeholder)
    if isinstance(data, str):
        return _sanitize_string(data, placeholder)
    return data


def _sanitize_string(value: str, placeholder: str) -> str:
    if not value:
        return value
    if _SECRET_TEMPLATE_PATTERN.search(value):
        return placeholder
    masked = value
    if _SK_PATTERN.search(masked):
        masked = _SK_PATTERN.sub(placeholder, masked)
    if _LONG_HEX_PATTERN.search(masked):
        masked = _LONG_HEX_PATTERN.sub(placeholder, masked)
    if _TOKEN_PATTERN.search(masked):
        masked = _TOKEN_PATTERN.sub(lambda match: match.group(0).replace(match.group(1), placeholder), masked)
    return masked


__all__ = ["sanitize_for_storage"]
