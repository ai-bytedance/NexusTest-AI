from celery import Celery
from kombu import Queue

from app.core.config import get_settings


def create_celery_app() -> Celery:
    settings = get_settings()
    celery_app = Celery(
        "app",
        broker=settings.redis_url,
        backend=settings.redis_url,
        include=["app.tasks"],
    )
    celery_app.conf.update(
        task_default_queue="cases",
        task_queues=(
            Queue("cases", routing_key="cases"),
            Queue("suites", routing_key="suites"),
        ),
        task_routes={
            "app.tasks.execute_case.execute_test_case": {"queue": "cases", "routing_key": "cases"},
            "app.tasks.execute_suite.execute_test_suite": {"queue": "suites", "routing_key": "suites"},
        },
    )
    return celery_app


celery_app = create_celery_app()
