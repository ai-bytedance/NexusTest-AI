from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict

from celery.schedules import crontab, schedule
from sqlalchemy import select

from app.core.celery import celery_app
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.logging import get_logger
from app.models import ExecutionPlan, ExecutionPlanType, ReportEntityType, ReportStatus, TestReport, TestSuite
from app.services.reports.progress import publish_progress_event
from app.services.scheduler.plan_service import (
    InvalidPlanConfiguration,
    compute_next_run_utc,
    ensure_suite_ids_exist,
    fetch_enabled_plans,
)
from app.tasks.execute_suite import execute_test_suite

logger = get_logger()


def _cron_schedule(expr: str, timezone_name: str):
    parts = expr.split()
    if len(parts) != 5:
        raise InvalidPlanConfiguration("Cron expression must have 5 fields")
    minute, hour, day_of_month, month_of_year, day_of_week = parts
    return crontab(
        minute=minute,
        hour=hour,
        day_of_month=day_of_month,
        month_of_year=month_of_year,
        day_of_week=day_of_week,
        tz=timezone_name,
    )


def _interval_schedule(interval_seconds: int):
    return schedule(run_every=interval_seconds)


@celery_app.task(name="app.tasks.scheduler.refresh_execution_plans")
def refresh_execution_plans() -> None:
    settings = get_settings()
    session = SessionLocal()
    try:
        plans = fetch_enabled_plans(session)
        dynamic_entries: Dict[str, dict] = {}
        for plan in plans:
            try:
                if plan.type == ExecutionPlanType.CRON:
                    schedule_obj = _cron_schedule(plan.cron_expr or "", plan.timezone)
                else:
                    schedule_obj = _interval_schedule(plan.interval_seconds or 0)
            except InvalidPlanConfiguration as exc:
                logger.warning(
                    "plan_schedule_invalid",
                    plan_id=str(plan.id),
                    error=str(exc),
                )
                continue

            dynamic_entries[f"execution_plan_{plan.id}"] = {
                "task": "app.tasks.scheduler.run_execution_plan",
                "args": (str(plan.id),),
                "schedule": schedule_obj,
            }

        base_schedule = {
            "refresh_execution_plans": {
                "task": "app.tasks.scheduler.refresh_execution_plans",
                "schedule": settings.plan_refresh_seconds,
            }
        }
        celery_app.conf.beat_schedule = {**base_schedule, **dynamic_entries}
        logger.info("scheduler_schedule_refreshed", plan_count=len(dynamic_entries))
    finally:
        session.close()


def _load_plan(session, plan_id: uuid.UUID) -> ExecutionPlan | None:
    stmt = select(ExecutionPlan).where(ExecutionPlan.id == plan_id, ExecutionPlan.is_deleted.is_(False))
    return session.execute(stmt).scalar_one_or_none()


@celery_app.task(name="app.tasks.scheduler.run_execution_plan", bind=True)
def run_execution_plan(self, plan_id: str) -> None:
    plan_uuid = uuid.UUID(plan_id)
    session = SessionLocal()
    try:
        plan = _load_plan(session, plan_uuid)
        if plan is None:
            logger.warning("plan_not_found", plan_id=plan_id)
            return
        if not plan.enabled:
            logger.info("plan_disabled_skip", plan_id=plan_id)
            return

        suite_ids = plan.suite_ids
        if not suite_ids:
            logger.warning("plan_no_suites", plan_id=plan_id)
            return

        ensure_suite_ids_exist(session, plan.project_id, suite_ids)

        now = datetime.now(timezone.utc)
        plan.last_run_at = now
        plan.next_run_at = compute_next_run_utc(
            plan.type,
            timezone_name=plan.timezone,
            cron_expr=plan.cron_expr,
            interval_seconds=plan.interval_seconds,
            reference=now,
        )
        session.add(plan)
        session.commit()

        stmt = (
            select(TestSuite)
            .where(TestSuite.id.in_(suite_ids), TestSuite.project_id == plan.project_id, TestSuite.is_deleted.is_(False))
        )
        suites = {suite.id: suite for suite in session.execute(stmt).scalars().all()}

        for suite_id in suite_ids:
            suite = suites.get(suite_id)
            if not suite:
                logger.warning("plan_suite_missing", plan_id=plan_id, suite_id=str(suite_id))
                continue

            report = TestReport(
                project_id=plan.project_id,
                entity_type=ReportEntityType.SUITE,
                entity_id=suite.id,
                status=ReportStatus.PENDING,
                metrics={"execution_plan_id": str(plan.id)},
            )
            session.add(report)
            session.commit()

            async_result = execute_test_suite.apply_async(
                kwargs={
                    "report_id": str(report.id),
                    "suite_id": str(suite.id),
                    "project_id": str(plan.project_id),
                },
                queue="suites",
            )

            report.metrics = {**(report.metrics or {}), "task_id": async_result.id}
            session.add(report)
            session.commit()

            publish_progress_event(
                str(report.id),
                "task_queued",
                payload={
                    "task_id": async_result.id,
                    "entity_type": report.entity_type.value,
                    "entity_id": str(report.entity_id),
                    "project_id": str(report.project_id),
                },
            )

        logger.info("plan_run_enqueued", plan_id=plan_id, suite_count=len(suite_ids))
    finally:
        session.close()


__all__ = ["refresh_execution_plans", "run_execution_plan"]
