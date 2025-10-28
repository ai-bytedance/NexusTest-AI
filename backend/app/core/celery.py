from celery import Celery

from app.core.config import get_settings


def create_celery_app() -> Celery:
    settings = get_settings()
    celery_app = Celery(
        "app",
        broker=settings.redis_url,
        backend=settings.redis_url,
        include=["app.tasks"],
    )
    celery_app.conf.update(task_default_queue="default")
    return celery_app


celery_app = create_celery_app()
