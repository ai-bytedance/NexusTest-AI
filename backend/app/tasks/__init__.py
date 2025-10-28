from app.core.celery import celery_app

# Import task modules so Celery discovers task definitions.
from app.tasks import execute_case, execute_suite  # noqa: F401

__all__ = ("celery_app",)
