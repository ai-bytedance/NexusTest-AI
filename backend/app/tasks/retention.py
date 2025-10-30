from __future__ import annotations

from dataclasses import asdict

from app.core.celery import celery_app
from app.db.session import SessionLocal
from app.logging import get_logger
from app.observability import track_task
from app.services.retention import RetentionService

logger = get_logger()


@celery_app.task(name="app.tasks.retention.run", bind=True, queue="cases")
def run_retention(self) -> dict:
    session = SessionLocal()
    try:
        service = RetentionService(session)
        with track_task("retention.run", queue="cases"):
            stats = service.purge()
            return asdict(stats)
    except Exception:  # noqa: BLE001
        logger.exception("retention_task_failed", task_id=self.request.id if hasattr(self, "request") else None)
        raise
    finally:
        session.close()
