from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User


def record_audit_log(
    session: Session,
    *,
    actor: User | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    project_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    log = AuditLog(
        actor_id=actor.id if actor else None,
        actor_email=actor.email if actor else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        project_id=project_id,
        organization_id=organization_id,
        metadata_=metadata or {},
        ip=ip,
        user_agent=user_agent,
    )
    session.add(log)
    return log


__all__ = ["record_audit_log"]
