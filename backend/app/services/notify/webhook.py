from __future__ import annotations

from typing import Any

import httpx

from app.logging import get_logger
from app.models.notifier_event import NotifierEventType
from app.services.notify.base import NotifierProvider, NotifierSendError

logger = get_logger()

_DEFAULT_TIMEOUT = 10.0


class WebhookProvider(NotifierProvider):
    def send(self, event: NotifierEventType, payload: dict[str, Any]) -> None:
        config = self.notifier.config or {}
        url = config.get("url")
        if not url:
            raise NotifierSendError("Webhook URL is not configured")
        headers = config.get("headers") if isinstance(config.get("headers"), dict) else {}

        body = {
            "event": event.value,
            "project_id": str(payload.get("project_id")),
            "message": payload.get("message"),
            "payload": payload,
        }

        try:
            response = httpx.post(url, json=body, headers=headers, timeout=_DEFAULT_TIMEOUT)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "webhook_provider_http_error",
                notifier_id=str(self.notifier.id),
                status_code=exc.response.status_code,
                response_text=exc.response.text,
            )
            raise NotifierSendError(f"Webhook responded with status {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "webhook_provider_request_error",
                notifier_id=str(self.notifier.id),
                error=str(exc),
            )
            raise NotifierSendError("Failed to send webhook notification") from exc


__all__ = ["WebhookProvider"]
