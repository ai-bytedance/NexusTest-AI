from __future__ import annotations

from typing import Any

import httpx

from app.logging import get_logger
from app.models.notifier_event import NotifierEventType
from app.services.notify.base import NotifierProvider, NotifierSendError

logger = get_logger()

_DEFAULT_TIMEOUT = 10.0


class SlackProvider(NotifierProvider):
    def send(self, event: NotifierEventType, payload: dict[str, Any]) -> None:
        config = self.notifier.config or {}
        url = config.get("url") or config.get("webhook")
        if not url:
            raise NotifierSendError("Slack webhook URL is not configured")

        channel = config.get("channel") or self.settings.slack_default_channel
        message = payload.get("message") or "Test execution update"

        body: dict[str, Any] = {
            "text": message,
        }
        if channel:
            body["channel"] = channel

        try:
            response = httpx.post(url, json=body, timeout=_DEFAULT_TIMEOUT)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "slack_provider_http_error",
                notifier_id=str(self.notifier.id),
                status_code=exc.response.status_code,
                response_text=exc.response.text,
            )
            raise NotifierSendError(
                f"Slack webhook responded with status {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "slack_provider_request_error",
                notifier_id=str(self.notifier.id),
                error=str(exc),
            )
            raise NotifierSendError("Failed to send Slack notification") from exc


__all__ = ["SlackProvider"]
