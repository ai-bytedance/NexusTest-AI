from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.core.config import get_settings
from app.models.notifier import Notifier, NotifierType
from app.models.notifier_event import NotifierEventType


class NotifierSendError(RuntimeError):
    """Raised when a notifier provider fails to deliver a message."""


class NotifierProvider(ABC):
    def __init__(self, notifier: Notifier) -> None:
        self.notifier = notifier
        self.settings = get_settings()

    @abstractmethod
    def send(self, event: NotifierEventType, payload: dict[str, Any]) -> None:
        """Send the notification for the given event."""


def get_provider(notifier: Notifier) -> NotifierProvider:
    if notifier.type == NotifierType.WEBHOOK:
        from app.services.notify.webhook import WebhookProvider

        return WebhookProvider(notifier)
    if notifier.type == NotifierType.EMAIL:
        from app.services.notify.email import EmailProvider

        return EmailProvider(notifier)
    if notifier.type == NotifierType.FEISHU:
        from app.services.notify.feishu import FeishuProvider

        return FeishuProvider(notifier)
    if notifier.type == NotifierType.SLACK:
        from app.services.notify.slack import SlackProvider

        return SlackProvider(notifier)
    if notifier.type == NotifierType.WECOM:
        from app.services.notify.wecom import WeComProvider

        return WeComProvider(notifier)
    if notifier.type == NotifierType.DINGTALK:
        from app.services.notify.dingtalk import DingTalkProvider

        return DingTalkProvider(notifier)
    raise NotifierSendError(f"Unsupported notifier type: {notifier.type}")


__all__ = ["NotifierProvider", "NotifierSendError", "get_provider"]
