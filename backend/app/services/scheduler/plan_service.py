from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from croniter.croniter import CroniterBadCronError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.execution_plan import ExecutionPlan, ExecutionPlanType
from app.models.test_suite import TestSuite


class InvalidPlanConfiguration(ValueError):
    """Raised when an execution plan has invalid schedule configuration."""


def resolve_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:  # pragma: no cover - defensive
        raise InvalidPlanConfiguration(f"Unknown timezone '{timezone_name}'") from exc


def validate_cron_expression(expr: str, tz: ZoneInfo) -> None:
    try:
        croniter(expr, datetime.now(tz))
    except (CroniterBadCronError, ValueError) as exc:
        raise InvalidPlanConfiguration(f"Invalid cron expression '{expr}'") from exc


def compute_next_run_utc(
    plan_type: ExecutionPlanType,
    *,
    timezone_name: str,
    cron_expr: str | None,
    interval_seconds: int | None,
    reference: datetime | None = None,
) -> datetime | None:
    reference_utc = reference or datetime.now(timezone.utc)

    if plan_type == ExecutionPlanType.CRON:
        if not cron_expr:
            raise InvalidPlanConfiguration("cron_expr is required for cron-based plans")
        tz = resolve_timezone(timezone_name)
        validate_cron_expression(cron_expr, tz)
        base = reference_utc.astimezone(tz)
        next_local = croniter(cron_expr, base).get_next(datetime)
        return next_local.astimezone(timezone.utc)

    if plan_type == ExecutionPlanType.INTERVAL:
        if not interval_seconds or interval_seconds <= 0:
            raise InvalidPlanConfiguration("interval_seconds must be greater than zero")
        return reference_utc + timedelta(seconds=interval_seconds)

    raise InvalidPlanConfiguration(f"Unsupported plan type '{plan_type}'")


def ensure_suite_ids_exist(
    db: Session,
    project_id: uuid.UUID,
    suite_ids: Iterable[uuid.UUID],
) -> list[uuid.UUID]:
    ids = list({uuid.UUID(str(item)) for item in suite_ids})
    if not ids:
        raise InvalidPlanConfiguration("At least one suite must be associated with the plan")
    stmt = (
        select(TestSuite.id)
        .where(
            TestSuite.project_id == project_id,
            TestSuite.id.in_(ids),
            TestSuite.is_deleted.is_(False),
        )
    )
    existing = {row[0] for row in db.execute(stmt).all()}
    missing = [item for item in ids if item not in existing]
    if missing:
        raise InvalidPlanConfiguration(
            "The following suite identifiers do not exist or are unavailable: "
            + ", ".join(str(item) for item in missing)
        )
    return ids


def fetch_enabled_plans(db: Session) -> Sequence[ExecutionPlan]:
    stmt = select(ExecutionPlan).where(
        ExecutionPlan.enabled.is_(True),
        ExecutionPlan.is_deleted.is_(False),
    )
    return db.execute(stmt).scalars().unique().all()


def update_plan_schedule(plan: ExecutionPlan, reference: datetime | None = None) -> None:
    if not plan.enabled:
        plan.next_run_at = None
        return
    plan.next_run_at = compute_next_run_utc(
        plan.type,
        timezone_name=plan.timezone,
        cron_expr=plan.cron_expr,
        interval_seconds=plan.interval_seconds,
        reference=reference,
    )


def serialize_plan(plan: ExecutionPlan) -> dict[str, object]:
    return {
        "id": str(plan.id),
        "project_id": str(plan.project_id),
        "name": plan.name,
        "type": plan.type.value,
        "cron_expr": plan.cron_expr,
        "interval_seconds": plan.interval_seconds,
        "enabled": plan.enabled,
        "timezone": plan.timezone,
        "last_run_at": plan.last_run_at.isoformat() if plan.last_run_at else None,
        "next_run_at": plan.next_run_at.isoformat() if plan.next_run_at else None,
        "suite_ids": [str(item) for item in plan.suite_ids],
    }


__all__ = [
    "InvalidPlanConfiguration",
    "compute_next_run_utc",
    "ensure_suite_ids_exist",
    "fetch_enabled_plans",
    "resolve_timezone",
    "update_plan_schedule",
    "validate_cron_expression",
]
