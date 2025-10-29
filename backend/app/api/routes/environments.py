from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import ProjectContext, require_project_member
from app.core.crypto import encrypt_secret_mapping
from app.core.errors import ErrorCode, http_exception
from app.db.session import get_db
from app.models.environment import Environment
from app.schemas.environment import EnvironmentCreate, EnvironmentRead, EnvironmentUpdate

router = APIRouter(prefix="/projects/{project_id}/environments", tags=["environments"])


def _mask_secrets(payload: dict[str, Any] | None) -> dict[str, bool]:
    if not payload or not isinstance(payload, dict):
        return {}
    return {key: True for key in payload.keys() if isinstance(key, str)}


def _serialize(environment: Environment) -> EnvironmentRead:
    raw = {
        "id": environment.id,
        "project_id": environment.project_id,
        "name": environment.name,
        "base_url": environment.base_url,
        "headers": environment.headers or {},
        "variables": environment.variables or {},
        "secrets": _mask_secrets(environment.secrets),
        "is_default": environment.is_default,
        "created_by": environment.created_by,
        "created_at": environment.created_at,
        "updated_at": environment.updated_at,
        "is_deleted": environment.is_deleted,
    }
    return EnvironmentRead.model_validate(raw)


def _get_environment(db: Session, project_id: UUID, environment_id: UUID) -> Environment:
    stmt = (
        select(Environment)
        .where(
            Environment.id == environment_id,
            Environment.project_id == project_id,
            Environment.is_deleted.is_(False),
        )
        .limit(1)
    )
    environment = db.execute(stmt).scalar_one_or_none()
    if environment is None:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Environment not found")
    return environment


def _apply_default_flag(db: Session, environment: Environment, *, make_default: bool) -> None:
    if not make_default:
        environment.is_default = False
        return
    db.execute(
        update(Environment)
        .where(
            Environment.project_id == environment.project_id,
            Environment.id != environment.id,
        )
        .values(is_default=False)
    )
    environment.is_default = True


@router.get("", response_model=ResponseEnvelope)
def list_environments(
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    stmt = (
        select(Environment)
        .where(
            Environment.project_id == context.project.id,
            Environment.is_deleted.is_(False),
        )
        .order_by(Environment.created_at.asc())
    )
    environments = db.execute(stmt).scalars().all()
    data = [_serialize(item) for item in environments]
    return success_response(data)


@router.post("", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
def create_environment(
    payload: EnvironmentCreate,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    encrypted_secrets = encrypt_secret_mapping(payload.secrets)
    environment = Environment(
        project_id=context.project.id,
        name=payload.name,
        base_url=payload.base_url,
        headers=payload.headers,
        variables=payload.variables,
        secrets=encrypted_secrets,
        is_default=payload.is_default,
        created_by=context.membership.user_id,
    )
    db.add(environment)
    db.flush()
    _apply_default_flag(db, environment, make_default=payload.is_default)
    db.commit()
    db.refresh(environment)
    return success_response(_serialize(environment))


@router.get("/{environment_id}", response_model=ResponseEnvelope)
def get_environment(
    environment_id: UUID,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    environment = _get_environment(db, context.project.id, environment_id)
    return success_response(_serialize(environment))


@router.patch("/{environment_id}", response_model=ResponseEnvelope)
def update_environment(
    environment_id: UUID,
    payload: EnvironmentUpdate,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    environment = _get_environment(db, context.project.id, environment_id)
    updates = payload.model_dump(exclude_unset=True)

    secrets_payload = updates.pop("secrets", None)
    if secrets_payload is not None:
        current = dict(environment.secrets or {})
        for key, value in secrets_payload.items():
            if value is None:
                current.pop(key, None)
            else:
                current[key] = encrypt_secret_mapping({key: value})[key]
        environment.secrets = current

    for field, value in updates.items():
        setattr(environment, field, value)

    _apply_default_flag(db, environment, make_default=bool(environment.is_default))

    db.add(environment)
    db.commit()
    db.refresh(environment)
    return success_response(_serialize(environment))


@router.delete("/{environment_id}", response_model=ResponseEnvelope)
def delete_environment(
    environment_id: UUID,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    environment = _get_environment(db, context.project.id, environment_id)
    environment.is_deleted = True
    if environment.is_default:
        environment.is_default = False
    db.add(environment)
    db.commit()
    return success_response({"id": environment.id, "deleted": True})


@router.post("/{environment_id}/default", response_model=ResponseEnvelope)
def set_default_environment(
    environment_id: UUID,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    environment = _get_environment(db, context.project.id, environment_id)
    _apply_default_flag(db, environment, make_default=True)
    db.add(environment)
    db.commit()
    db.refresh(environment)
    return success_response(_serialize(environment))
