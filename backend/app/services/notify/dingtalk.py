from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any
from urllib.parse import quote_plus

import httpx

from app.logging import get_logger
from app.models.notifier_event import NotifierEventType
from app.services.notify.base import NotifierProvider, NotifierSendError

logger = get_logger()

_DEFAULT_TIMEOUT = 10.0
_MAX_LOG_SNIPPET = 512


def _append_signature(url: str, secret: str) -> str:
    timestamp = str(int(time.time()))
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), string_to_sign, hashlib.sha256).digest()
    signature = quote_plus(base64.b64encode(digest).decode("utf-8"))
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}timestamp={timestamp}&sign={signature}"


def _derive_title(payload: dict[str, Any]) -> str:
    project = (payload.get("project_name") or "Notification").strip()
    status = str(payload.get("status") or "update").replace("_", " ").title()
    entity = (payload.get("entity_name") or payload.get("entity_id") or "").strip()
    base = f"{project} {entity}".strip()
    title = f"{base} {status}" if base else f"{project} {status}"
    title = title.strip() or "Notification"
    return title[:80]


def _build_payload(payload: dict[str, Any]) -> dict[str, Any]:
    markdown = payload.get("markdown")
    if markdown:
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": _derive_title(payload),
                "text": str(markdown),
            },
        }
    text = payload.get("text") or payload.get("message") or "Test execution update"
    return {
        "msgtype": "text",
        "text": {
            "content": str(text),
        },
    }


class DingTalkProvider(NotifierProvider):
    def send(self, event: NotifierEventType, payload: dict[str, Any]) -> None:
        config = self.notifier.config or {}
        url = config.get("url") or config.get("webhook")
        if not url:
            raise NotifierSendError("DingTalk webhook URL is not configured")

        secret = config.get("secret") or config.get("signing_secret")
        signed_url = _append_signature(url, secret) if secret else url
        body = _build_payload(payload)

        try:
            response = httpx.post(signed_url, json=body, timeout=_DEFAULT_TIMEOUT)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "dingtalk_provider_http_error",
                notifier_id=str(self.notifier.id),
                status_code=exc.response.status_code,
                response_text=(exc.response.text or "")[:_MAX_LOG_SNIPPET],
            )
            raise NotifierSendError(
                f"DingTalk webhook responded with status {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "dingtalk_provider_request_error",
                notifier_id=str(self.notifier.id),
                error=str(exc),
            )
            raise NotifierSendError("Failed to send DingTalk notification") from exc


__all__ = ["DingTalkProvider"]
