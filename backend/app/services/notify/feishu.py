from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any

import httpx

from app.logging import get_logger
from app.models.notifier_event import NotifierEventType
from app.services.notify.base import NotifierProvider, NotifierSendError

logger = get_logger()

_DEFAULT_TIMEOUT = 10.0


class FeishuProvider(NotifierProvider):
    def send(self, event: NotifierEventType, payload: dict[str, Any]) -> None:
        config = self.notifier.config or {}
        url = config.get("url") or config.get("webhook")
        if not url:
            raise NotifierSendError("Feishu webhook URL is not configured")

        message = payload.get("message") or "Test execution update"
        body: dict[str, Any] = {
            "msg_type": "text",
            "content": {
                "text": message,
            },
        }

        secret = (
            config.get("secret")
            or config.get("signing_secret")
            or self.settings.feishu_signing_secret
        )
        if secret:
            timestamp = str(int(time.time()))
            string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
            digest = hmac.new(secret.encode("utf-8"), string_to_sign, hashlib.sha256).digest()
            body["timestamp"] = timestamp
            body["sign"] = base64.b64encode(digest).decode("utf-8")

        try:
            response = httpx.post(url, json=body, timeout=_DEFAULT_TIMEOUT)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "feishu_provider_http_error",
                notifier_id=str(self.notifier.id),
                status_code=exc.response.status_code,
                response_text=exc.response.text,
            )
            raise NotifierSendError(
                f"Feishu webhook responded with status {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "feishu_provider_request_error",
                notifier_id=str(self.notifier.id),
                error=str(exc),
            )
            raise NotifierSendError("Failed to send Feishu notification") from exc


__all__ = ["FeishuProvider"]
