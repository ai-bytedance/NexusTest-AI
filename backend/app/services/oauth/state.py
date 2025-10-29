from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.core.config import get_settings
from app.core.errors import ErrorCode, http_exception

STATE_ISSUER = "oauth_state"


def create_oauth_state(provider: str, action: str, redirect_uri: str | None, user_id: str | None = None) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "iss": STATE_ISSUER,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.sso_state_ttl_seconds)).timestamp()),
        "jti": secrets.token_urlsafe(16),
        "provider": provider,
        "action": action,
    }
    if redirect_uri:
        payload["redirect_uri"] = redirect_uri
    if user_id:
        payload["user_id"] = user_id
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def parse_oauth_state(state: str, expected_provider: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(state, settings.secret_key, algorithms=["HS256"])
    except JWTError as exc:  # pragma: no cover - library validation
        raise http_exception(400, ErrorCode.AUTH_SSO_STATE_INVALID, "Invalid OAuth state") from exc

    if payload.get("iss") != STATE_ISSUER:
        raise http_exception(400, ErrorCode.AUTH_SSO_STATE_INVALID, "Invalid OAuth state issuer")
    if payload.get("provider") != expected_provider:
        raise http_exception(400, ErrorCode.AUTH_SSO_STATE_INVALID, "OAuth state provider mismatch")
    return payload
