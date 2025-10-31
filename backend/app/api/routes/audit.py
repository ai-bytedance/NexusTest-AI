from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import get_current_user, require_project_admin
from app.core.errors import ErrorCode, http_exception
from app.db.session import get_db
from app.models import AuditLog, User

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs", response_model=ResponseEnvelope)
def export_audit_logs(
    request: Request,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    action: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if start is None and end is None:
        # default to last 24 hours
        end = datetime.now(timezone.utc)
        start = end - (end - end.replace(hour=0, minute=0, second=0, microsecond=0))
    if start and end and start > end:
        raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "start must be before end")

    conditions: list[Any] = []
    if project_id:
        try:
            import uuid

            conditions.append(AuditLog.project_id == uuid.UUID(project_id))
        except Exception:
            raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "Invalid project_id")
    if action:
        conditions.append(AuditLog.action == action)
    if start:
        conditions.append(AuditLog.created_at >= start)
    if end:
        conditions.append(AuditLog.created_at <= end)

    stmt = select(AuditLog).where(and_(*conditions)) if conditions else select(AuditLog)
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)
    items = db.execute(stmt).scalars().all()
    payload = [
        {
            "id": str(row.id),
            "actor_id": str(row.actor_id) if row.actor_id else None,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "project_id": str(row.project_id) if row.project_id else None,
            "organization_id": str(row.organization_id) if row.organization_id else None,
            "metadata": row.metadata,
            "ip": row.ip,
            "user_agent": row.user_agent,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in items
    ]
    return success_response({"items": payload, "count": len(payload)})
