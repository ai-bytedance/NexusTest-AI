from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.logging import get_logger
from app.models import NotifierEvent, NotifierEventStatus
from app.services.notify.base import NotifierSendError, get_provider

logger = get_logger()


def _load_event(session: Session, event_id: uuid.UUID) -> NotifierEvent | None:
    stmt = (
        select(NotifierEvent)
        .where(NotifierEvent.id == event_id, NotifierEvent.is_deleted.is_(False))
        .options(selectinload(NotifierEvent.notifier))
    )
    return session.execute(stmt).scalar_one_or_none()


from app.core.celery import celery_app


@celery_app.task(name="app.tasks.notifications.dispatch_notifier_event", bind=True)
def dispatch_notifier_event(self, event_id: str) -> None:
    settings = get_settings()
    event_uuid = uuid.UUID(event_id)
    session = SessionLocal()

    try:
        event = _load_event(session, event_uuid)
        if event is None:
            logger.warning("notifier_event_missing", event_id=event_id)
            return
        if event.status == NotifierEventStatus.SUCCESS:
            return
        if event.notifier is None or event.notifier.is_deleted or not event.notifier.enabled:
            logger.info("notifier_disabled_skip", notifier_id=str(event.notifier_id), event_id=event_id)
            event.status = NotifierEventStatus.FAILED
            event.error_message = "Notifier is disabled"
            event.processed_at = datetime.now(timezone.utc)
            session.add(event)
            session.commit()
            return

        provider = get_provider(event.notifier)
        provider.send(event.event, dict(event.payload or {}))

        event.status = NotifierEventStatus.SUCCESS
        event.error_message = None
        event.retry_count = self.request.retries
        event.processed_at = datetime.now(timezone.utc)
        session.add(event)
        session.commit()

    except NotifierSendError as exc:
        session.rollback()
        _handle_retry(self, session, settings, event_uuid, str(exc), is_provider_error=True)
    except Exception as exc:  # pragma: no cover - guardrail
        session.rollback()
        _handle_retry(self, session, settings, event_uuid, str(exc), is_provider_error=False)
    finally:
        session.close()


def _handle_retry(
    task,  # type: ignore[no-untyped-def]
    session: Session,
    settings,
    event_id: uuid.UUID,
    message: str,
    *,
    is_provider_error: bool,
) -> None:
    """Handle retry or fail logic for notifier dispatch."""

    event = _load_event(session, event_id)
    if event is None:
        logger.warning("notifier_event_missing_on_retry", event_id=str(event_id), message=message)
        return

    retries = task.request.retries
    event.retry_count = retries
    event.error_message = message
    session.add(event)
    session.commit()

    called_directly = bool(getattr(task.request, "called_directly", False))
    max_retries = max(0, int(settings.notify_max_retries))

    if called_directly or retries >= max_retries:
        logger.error(
            "notifier_event_failed",
            event_id=str(event_id),
            notifier_id=str(event.notifier_id),
            message=message,
            retries=retries,
            provider_error=is_provider_error,
        )
        event.status = NotifierEventStatus.FAILED
        event.processed_at = datetime.now(timezone.utc)
        session.add(event)
        session.commit()
        raise NotifierSendError(message)

    backoff = max(1, int(settings.notify_backoff_seconds)) * max(1, 2 ** retries)
    logger.warning(
        "notifier_event_retry",
        event_id=str(event_id),
        notifier_id=str(event.notifier_id),
        retries=retries,
        next_retry_in_seconds=backoff,
    )

    raise task.retry(exc=NotifierSendError(message), countdown=backoff)


__all__ = ["dispatch_notifier_event"]
