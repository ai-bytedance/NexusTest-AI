from __future__ import annotations

import json
from typing import Any

import httpx

from app.logging import get_logger
from app.models.notifier_event import NotifierEventType
from app.services.notify.base import NotifierProvider, NotifierSendError
from app.services.notify.signing import build_signature_headers

logger = get_logger()

_DEFAULT_TIMEOUT = 10.0


class WebhookProvider(NotifierProvider):
    def send(self, event: NotifierEventType, payload: dict[str, Any]) -> None:
        config = self.notifier.config or {}
        url = config.get("url")
        if not url:
            raise NotifierSendError("Webhook URL is not configured")

        extra_headers = config.get("headers") if isinstance(config.get("headers"), dict) else {}
        headers: dict[str, str] = {}
        for key, value in extra_headers.items():
            if value is None:
                continue
            headers[str(key)] = str(value)
        headers.setdefault("Content-Type", "application/json")

        secret = config.get("secret") or config.get("signing_secret")
        if not secret:
            raise NotifierSendError("Webhook signing secret is not configured")

        body = {
            "event": event.value,
            "project_id": str(payload.get("project_id")),
            "message": payload.get("message"),
            "payload": payload,
        }
        body_bytes = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")

        if secret:
            try:
                headers.update(build_signature_headers(secret, body_bytes))
            except ValueError as exc:  # pragma: no cover - defensive
                raise NotifierSendError("Webhook signing secret is invalid") from exc

        try:
            response = httpx.post(url, content=body_bytes, headers=headers, timeout=_DEFAULT_TIMEOUT)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "webhook_provider_http_error",
                notifier_id=str(self.notifier.id),
                status_code=exc.response.status_code,
                response_text=(exc.response.text or "")[:512],
            )
            raise NotifierSendError(
                f"Webhook responded with status {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "webhook_provider_request_error",
                notifier_id=str(self.notifier.id),
                error=str(exc),
            )
            raise NotifierSendError("Failed to send webhook notification") from exc


__all__ = ["WebhookProvider"]
