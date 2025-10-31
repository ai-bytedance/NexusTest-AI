from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import ProjectContext, get_current_user, require_project_admin, require_project_member
from app.core.errors import ErrorCode, http_exception
from app.db.session import get_db
from app.models import ApiToken, RateLimitPolicy, AuditLog
from app.models.user import User
from app.schemas.rate_limit import (
    EffectiveRateLimit,
    RateLimitPolicyCreate,
    RateLimitPolicyDefaultUpdate,
    RateLimitPolicyRead,
    RateLimitPolicyUpdate,
    RateLimitRule,
)
from app.services.rate_limit.service import RateLimitService

router = APIRouter(prefix="/projects/{project_id}/rate-limit-policies", tags=["rate-limits"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _serialize_policy(policy) -> dict:
    schema = RateLimitPolicyRead.model_validate(policy)
    return schema.model_dump(mode="json")


@router.get("", response_model=ResponseEnvelope)
def list_policies(
    request: Request,
    context: ProjectContext = Depends(require_project_admin),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    service = RateLimitService(
        db,
        actor=current_user,
        project=context.project,
        client_ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    policies = service.list_policies()
    data = [_serialize_policy(policy) for policy in policies]
    return success_response(data)


@router.post("", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
def create_policy(
    payload: RateLimitPolicyCreate,
    request: Request,
    context: ProjectContext = Depends(require_project_admin),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    service = RateLimitService(
        db,
        actor=current_user,
        project=context.project,
        client_ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    policy = service.create_policy(payload)
    return success_response(_serialize_policy(policy))


@router.patch("/{policy_id}", response_model=ResponseEnvelope)
def update_policy(
    policy_id: UUID,
    payload: RateLimitPolicyUpdate,
    request: Request,
    context: ProjectContext = Depends(require_project_admin),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    service = RateLimitService(
        db,
        actor=current_user,
        project=context.project,
        client_ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    policy = service.get_policy(policy_id)
    updated = service.update_policy(policy, payload)
    return success_response(_serialize_policy(updated))


@router.delete("/{policy_id}", response_model=ResponseEnvelope)
def delete_policy(
    policy_id: UUID,
    request: Request,
    context: ProjectContext = Depends(require_project_admin),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    service = RateLimitService(
        db,
        actor=current_user,
        project=context.project,
        client_ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    policy = service.get_policy(policy_id)
    service.delete_policy(policy)
    return success_response({"id": str(policy_id), "deleted": True})


@router.put("/default", response_model=ResponseEnvelope)
def set_default_policy(
    payload: RateLimitPolicyDefaultUpdate,
    request: Request,
    context: ProjectContext = Depends(require_project_admin),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    service = RateLimitService(
        db,
        actor=current_user,
        project=context.project,
        client_ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    policy_obj: RateLimitPolicy | None = None
    if payload.policy_id is not None:
        policy_obj = service.get_policy(payload.policy_id)
    project = service.set_default_policy(policy_obj)
    default_policy = project.default_rate_limit_policy
    default_schema = RateLimitPolicyRead.model_validate(default_policy).model_dump(mode="json") if default_policy else None
    return success_response({"default_policy": default_schema})


@router.get("/effective", response_model=ResponseEnvelope)
def effective_limits(
    request: Request,
    context: ProjectContext = Depends(require_project_member),
    token_id: UUID | None = Query(default=None, description="Optional token to evaluate"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    default_policy = context.project.default_rate_limit_policy if context.project.default_rate_limit_policy and context.project.default_rate_limit_policy.enabled else None
    token_policy_obj: RateLimitPolicy | None = None

    if token_id is not None:
        token = db.get(ApiToken, token_id)
        if token is None or token.user_id != current_user.id:
            raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Token not found")
        if token.rate_limit_policy_id:
            candidate = db.get(RateLimitPolicy, token.rate_limit_policy_id)
            if candidate and candidate.enabled and (candidate.project_id is None or candidate.project_id == context.project.id):
                token_policy_obj = candidate

    active_rules: list[RateLimitRule] = []
    if default_policy:
        active_rules.extend(RateLimitRule.model_validate(rule) for rule in default_policy.rules)
    if token_policy_obj:
        active_rules.extend(RateLimitRule.model_validate(rule) for rule in token_policy_obj.rules)

    payload = EffectiveRateLimit(
        project_id=context.project.id,
        default_policy=RateLimitPolicyRead.model_validate(default_policy) if default_policy else None,
        token_policy=RateLimitPolicyRead.model_validate(token_policy_obj) if token_policy_obj else None,
        active_rules=active_rules,
    )
    return success_response(payload.model_dump(mode="json"))


@router.get("/throttles", response_model=ResponseEnvelope)
def recent_throttles(
    request: Request,
    context: ProjectContext = Depends(require_project_admin),
    limit: int = Query(50, ge=1, le=200),
    since_minutes: int = Query(60, ge=1, le=1440),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    stmt = (
        db.query(AuditLog)
        .filter(
            AuditLog.project_id == context.project.id,
            AuditLog.action == "rate_limit.throttled",
            AuditLog.created_at >= cutoff,
        )
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    items = [
        {
            "id": str(row.id),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "metadata": row.metadata,
            "ip": row.ip,
            "user_agent": row.user_agent,
        }
        for row in stmt.all()
    ]
    return success_response({"items": items, "count": len(items)})
