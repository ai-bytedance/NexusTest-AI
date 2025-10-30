from __future__ import annotations

from app.core.celery import celery_app
from app.db.session import SessionLocal
from app.logging import get_logger
from app.observability import track_task
from app.services.backups import BackupManager

logger = get_logger()


@celery_app.task(name="app.tasks.backups.run_backup", bind=True, queue="cases")
def run_backup(self, triggered_by: str | None = None) -> str:
    session = SessionLocal()
    try:
        manager = BackupManager(session)
        with track_task("backups.run_backup", queue="cases"):
            backup = manager.run_backup(triggered_by=triggered_by or "celery")
            return str(backup.id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("backup_task_failed", task_id=self.request.id if hasattr(self, "request") else None)
        raise
    finally:
        session.close()
