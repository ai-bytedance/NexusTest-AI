from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import ProjectContext, require_project_admin, require_project_member
from app.core.errors import ErrorCode, http_exception
from app.db.session import get_db
from app.models import ExecutionPlan, ExecutionPlanType
from app.schemas.execution_plan import (
    ExecutionPlanCreate,
    ExecutionPlanRead,
    ExecutionPlanRunResponse,
    ExecutionPlanUpdate,
)
from app.services.scheduler.plan_service import (
    InvalidPlanConfiguration,
    compute_next_run_utc,
    ensure_suite_ids_exist,
    resolve_timezone,
    validate_cron_expression,
)
from app.tasks.scheduler import run_execution_plan

router = APIRouter(prefix="/projects/{project_id}/plans", tags=["execution-plans"])


def _get_plan(db: Session, project_id: UUID, plan_id: UUID) -> ExecutionPlan:
    stmt = (
        select(ExecutionPlan)
        .where(
            ExecutionPlan.id == plan_id,
            ExecutionPlan.project_id == project_id,
            ExecutionPlan.is_deleted.is_(False),
        )
        .limit(1)
    )
    plan = db.execute(stmt).scalar_one_or_none()
    if plan is None:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Execution plan not found")
    return plan


def _ensure_unique_name(db: Session, project_id: UUID, name: str, exclude_id: UUID | None = None) -> None:
    stmt = select(ExecutionPlan).where(
        ExecutionPlan.project_id == project_id,
        ExecutionPlan.name == name,
        ExecutionPlan.is_deleted.is_(False),
    )
    if exclude_id is not None:
        stmt = stmt.where(ExecutionPlan.id != exclude_id)
    conflict = db.execute(stmt).scalar_one_or_none()
    if conflict:
        raise http_exception(status.HTTP_409_CONFLICT, ErrorCode.CONFLICT, "Execution plan name already exists")


def _serialize_plan(plan: ExecutionPlan) -> ExecutionPlanRead:
    return ExecutionPlanRead.model_validate(plan)


def _compute_next_run(plan: ExecutionPlan) -> datetime | None:
    if not plan.enabled:
        return None
    return compute_next_run_utc(
        plan.type,
        timezone_name=plan.timezone,
        cron_expr=plan.cron_expr,
        interval_seconds=plan.interval_seconds,
        reference=datetime.now(timezone.utc),
    )


@router.post("", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
def create_plan(
    payload: ExecutionPlanCreate,
    context: ProjectContext = Depends(require_project_admin),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_unique_name(db, context.project.id, payload.name)

    ensure_suite_ids_exist(db, context.project.id, payload.suite_ids)

    if payload.type == ExecutionPlanType.CRON:
        tz = resolve_timezone(payload.timezone)
        validate_cron_expression(payload.cron_expr or "", tz)

    plan = ExecutionPlan(
        project_id=context.project.id,
        name=payload.name,
        type=payload.type,
        cron_expr=payload.cron_expr,
        interval_seconds=payload.interval_seconds,
        enabled=payload.enabled,
        timezone=payload.timezone,
        created_by=context.membership.user_id,
    )
    plan.set_suite_ids(payload.suite_ids)

    if plan.enabled:
        try:
            plan.next_run_at = _compute_next_run(plan)
        except InvalidPlanConfiguration as exc:
            raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, str(exc)) from exc
    else:
        plan.next_run_at = None

    db.add(plan)
    db.commit()
    db.refresh(plan)

    response = _serialize_plan(plan)
    return success_response(response.model_dump())


@router.get("", response_model=ResponseEnvelope)
def list_plans(
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    stmt = (
        select(ExecutionPlan)
        .where(
            ExecutionPlan.project_id == context.project.id,
            ExecutionPlan.is_deleted.is_(False),
        )
        .order_by(ExecutionPlan.created_at.desc())
    )
    plans = db.execute(stmt).scalars().all()
    data: List[dict] = [_serialize_plan(plan).model_dump() for plan in plans]
    return success_response(data)


@router.get("/{plan_id}", response_model=ResponseEnvelope)
def get_plan(
    plan_id: UUID,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    plan = _get_plan(db, context.project.id, plan_id)
    response = _serialize_plan(plan)
    return success_response(response.model_dump())


@router.patch("/{plan_id}", response_model=ResponseEnvelope)
def update_plan(
    plan_id: UUID,
    payload: ExecutionPlanUpdate,
    context: ProjectContext = Depends(require_project_admin),
    db: Session = Depends(get_db),
) -> dict:
    plan = _get_plan(db, context.project.id, plan_id)
    updates = payload.model_dump(exclude_unset=True)

    if "name" in updates and updates["name"] != plan.name:
        _ensure_unique_name(db, context.project.id, updates["name"], exclude_id=plan.id)
        plan.name = updates["name"]

    new_type = updates.get("type")
    if new_type and new_type != plan.type:
        plan.type = new_type
        if new_type == ExecutionPlanType.CRON:
            plan.interval_seconds = None
        else:
            plan.cron_expr = None

    if "cron_expr" in updates:
        plan.cron_expr = updates["cron_expr"]
    if "interval_seconds" in updates:
        plan.interval_seconds = updates["interval_seconds"]
    if "enabled" in updates:
        plan.enabled = updates["enabled"]
    if "timezone" in updates and updates["timezone"]:
        plan.timezone = updates["timezone"]
    if "suite_ids" in updates and updates["suite_ids"] is not None:
        suite_ids: Iterable[UUID] = updates["suite_ids"]
        ensure_suite_ids_exist(db, context.project.id, suite_ids)
        plan.set_suite_ids(suite_ids)

    if plan.enabled:
        try:
            tz = resolve_timezone(plan.timezone)
            if plan.type == ExecutionPlanType.CRON:
                validate_cron_expression(plan.cron_expr or "", tz)
            plan.next_run_at = _compute_next_run(plan)
        except InvalidPlanConfiguration as exc:
            raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, str(exc)) from exc
    else:
        plan.next_run_at = None

    db.add(plan)
    db.commit()
    db.refresh(plan)

    response = _serialize_plan(plan)
    return success_response(response.model_dump())


@router.delete("/{plan_id}", response_model=ResponseEnvelope)
def delete_plan(
    plan_id: UUID,
    context: ProjectContext = Depends(require_project_admin),
    db: Session = Depends(get_db),
) -> dict:
    plan = _get_plan(db, context.project.id, plan_id)
    if plan.is_deleted:
        return success_response({"id": plan.id, "deleted": True})

    plan.is_deleted = True
    db.add(plan)
    db.commit()

    return success_response({"id": plan.id, "deleted": True})


@router.post("/{plan_id}/run-now", response_model=ResponseEnvelope, status_code=status.HTTP_202_ACCEPTED)
def run_plan_now(
    plan_id: UUID,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    plan = _get_plan(db, context.project.id, plan_id)
    if not plan.suite_ids:
        raise http_exception(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.BAD_REQUEST,
            "Execution plan must have at least one suite configured",
        )

    async_result = run_execution_plan.apply_async(args=(str(plan.id),))
    response = ExecutionPlanRunResponse(task_id=async_result.id, plan_id=plan.id)
    return success_response(response.model_dump())


__all__ = [
    "create_plan",
    "list_plans",
    "get_plan",
    "update_plan",
    "delete_plan",
    "run_plan_now",
]
