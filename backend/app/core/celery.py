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
            Queue("retries", routing_key="retries"),
        ),
        task_routes={
            "app.tasks.execute_case.execute_test_case": {"queue": "cases", "routing_key": "cases"},
            "app.tasks.execute_suite.execute_test_suite": {"queue": "suites", "routing_key": "suites"},
        },
        beat_schedule={
            "refresh_execution_plans": {
                "task": "app.tasks.scheduler.refresh_execution_plans",
                "schedule": settings.plan_refresh_seconds,
            }
        },
        worker_concurrency=settings.celery_worker_concurrency,
        worker_prefetch_multiplier=settings.celery_worker_prefetch_multiplier,
        task_acks_late=settings.celery_task_acks_late,
        task_reject_on_worker_lost=settings.celery_task_reject_on_worker_lost,
        broker_transport_options={"visibility_timeout": settings.celery_visibility_timeout_seconds},
        timezone="UTC",
    )
    return celery_app


celery_app = create_celery_app()
