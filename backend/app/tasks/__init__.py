from app.core.celery_app import celery_app

# Import task modules so Celery discovers task definitions.
from app.tasks import (  # noqa: F401
    analytics,
    backups,
    execute_case,
    execute_suite,
    notifications,
    retention,
    scheduler,
)

__all__ = ("celery_app",)
