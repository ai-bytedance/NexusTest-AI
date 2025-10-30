from celery import Celery
from celery.schedules import crontab
from kombu import Queue

from app.core.config import get_settings
from app.logging import get_logger

logger = get_logger()


def _parse_cron(expression: str):
    parts = expression.split()
    if len(parts) != 5:
        raise ValueError("Cron expressions must have exactly five fields")
    minute, hour, day_of_month, month_of_year, day_of_week = parts
    return crontab(
        minute=minute,
        hour=hour,
        day_of_month=day_of_month,
        month_of_year=month_of_year,
        day_of_week=day_of_week,
    )


def create_celery_app() -> Celery:
    settings = get_settings()
    celery_app = Celery(
        "app",
        broker=settings.redis_url,
        backend=settings.redis_url,
        include=["app.tasks"],
    )

    try:
        backup_schedule = _parse_cron(settings.backup_job_cron)
    except ValueError:
        logger.warning("invalid_backup_cron_expression", expression=settings.backup_job_cron)
        backup_schedule = crontab(hour=2, minute=0)

    try:
        retention_schedule = _parse_cron(settings.retention_job_cron)
    except ValueError:
        logger.warning("invalid_retention_cron_expression", expression=settings.retention_job_cron)
        retention_schedule = crontab(hour=3, minute=0)

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
            },
            "process_failure_analytics": {
                "task": "app.tasks.analytics.process_failure_analytics",
                "schedule": 120,
            },
            "nightly_backup": {
                "task": "app.tasks.backups.run_backup",
                "schedule": backup_schedule,
                "kwargs": {"triggered_by": "celery"},
            },
            "retention_maintenance": {
                "task": "app.tasks.retention.run",
                "schedule": retention_schedule,
            },
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
