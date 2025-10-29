from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import ProjectContext, require_project_admin, require_project_member
from app.core.errors import ErrorCode, http_exception
from app.db.session import get_db
from app.models import Notifier, NotifierEventType
from app.schemas.notifier import NotifierCreate, NotifierRead, NotifierTestRequest, NotifierUpdate
from app.services.notify.base import NotifierSendError, get_provider

router = APIRouter(prefix="/projects/{project_id}/notifiers", tags=["notifications"])


def _ensure_unique_name(db: Session, project_id: UUID, name: str, exclude_id: UUID | None = None) -> None:
    stmt = select(Notifier).where(
        Notifier.project_id == project_id,
        Notifier.name == name,
        Notifier.is_deleted.is_(False),
    )
    if exclude_id is not None:
        stmt = stmt.where(Notifier.id != exclude_id)
    conflict = db.execute(stmt).scalar_one_or_none()
    if conflict:
        raise http_exception(status.HTTP_409_CONFLICT, ErrorCode.CONFLICT, "Notifier name already exists")


def _get_notifier(db: Session, project_id: UUID, notifier_id: UUID) -> Notifier:
    stmt = (
        select(Notifier)
        .where(
            Notifier.id == notifier_id,
            Notifier.project_id == project_id,
            Notifier.is_deleted.is_(False),
        )
        .limit(1)
    )
    notifier = db.execute(stmt).scalar_one_or_none()
    if notifier is None:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Notifier not found")
    return notifier


def _serialize_notifier(notifier: Notifier) -> NotifierRead:
    return NotifierRead.model_validate(notifier)


@router.post("", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
def create_notifier(
    payload: NotifierCreate,
    context: ProjectContext = Depends(require_project_admin),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_unique_name(db, context.project.id, payload.name)

    notifier = Notifier(
        project_id=context.project.id,
        name=payload.name,
        type=payload.type,
        config=payload.config,
        enabled=payload.enabled,
        created_by=context.membership.user_id,
    )
    db.add(notifier)
    db.commit()
    db.refresh(notifier)

    response = _serialize_notifier(notifier)
    return success_response(response.model_dump())


@router.get("", response_model=ResponseEnvelope)
def list_notifiers(
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    stmt = (
        select(Notifier)
        .where(
            Notifier.project_id == context.project.id,
            Notifier.is_deleted.is_(False),
        )
        .order_by(Notifier.created_at.desc())
    )
    notifiers = db.execute(stmt).scalars().all()
    data: List[dict] = [_serialize_notifier(item).model_dump() for item in notifiers]
    return success_response(data)


@router.patch("/{notifier_id}", response_model=ResponseEnvelope)
def update_notifier(
    notifier_id: UUID,
    payload: NotifierUpdate,
    context: ProjectContext = Depends(require_project_admin),
    db: Session = Depends(get_db),
) -> dict:
    notifier = _get_notifier(db, context.project.id, notifier_id)
    updates = payload.model_dump(exclude_unset=True)

    if "name" in updates and updates["name"] != notifier.name:
        _ensure_unique_name(db, context.project.id, updates["name"], exclude_id=notifier.id)
        notifier.name = updates["name"]
    if "type" in updates and updates["type"]:
        notifier.type = updates["type"]
    if "config" in updates and updates["config"] is not None:
        notifier.config = updates["config"]
    if "enabled" in updates:
        notifier.enabled = updates["enabled"]

    db.add(notifier)
    db.commit()
    db.refresh(notifier)

    response = _serialize_notifier(notifier)
    return success_response(response.model_dump())


@router.delete("/{notifier_id}", response_model=ResponseEnvelope)
def delete_notifier(
    notifier_id: UUID,
    context: ProjectContext = Depends(require_project_admin),
    db: Session = Depends(get_db),
) -> dict:
    notifier = _get_notifier(db, context.project.id, notifier_id)
    if notifier.is_deleted:
        return success_response({"id": notifier.id, "deleted": True})

    notifier.is_deleted = True
    db.add(notifier)
    db.commit()

    return success_response({"id": notifier.id, "deleted": True})


@router.post("/{notifier_id}/test", response_model=ResponseEnvelope)
def send_test_notification(
    notifier_id: UUID,
    payload: NotifierTestRequest,
    context: ProjectContext = Depends(require_project_admin),
    db: Session = Depends(get_db),
) -> dict:
    notifier = _get_notifier(db, context.project.id, notifier_id)
    provider = get_provider(notifier)
    message = payload.message or f"Test notification for project {context.project.name}"
    test_payload = {
        "project_id": str(context.project.id),
        "project_name": context.project.name,
        "message": message,
        "event": NotifierEventType.RUN_FINISHED.value,
    }

    try:
        provider.send(NotifierEventType.RUN_FINISHED, test_payload)
    except NotifierSendError as exc:
        raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, str(exc)) from exc

    return success_response({"sent": True})


__all__ = [
    "create_notifier",
    "list_notifiers",
    "update_notifier",
    "delete_notifier",
    "send_test_notification",
]
