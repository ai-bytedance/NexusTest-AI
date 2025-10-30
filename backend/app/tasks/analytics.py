from __future__ import annotations

from app.core.celery import celery_app
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.observability import track_task
from app.services.analytics.processor import FailureAnalyticsProcessor


@celery_app.task(name="app.tasks.analytics.process_failure_analytics", queue="cases")
def process_failure_analytics(batch_size: int = 200) -> int:
    settings = get_settings()
    session = SessionLocal()
    with track_task("process_failure_analytics", queue="cases"):
        try:
            processor = FailureAnalyticsProcessor(session, settings)
            return processor.process_pending(batch_size=batch_size)
        finally:
            session.close()
