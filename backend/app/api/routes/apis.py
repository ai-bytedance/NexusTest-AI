from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import ProjectContext, require_project_member
from app.core.errors import ErrorCode, http_exception
from app.db.session import get_db
from app.models.api import Api
from app.schemas.api import ApiCreate, ApiRead, ApiUpdate

router = APIRouter(prefix="/projects/{project_id}/apis", tags=["apis"])


def _get_api(db: Session, project_id: UUID, api_id: UUID) -> Api:
    api = db.execute(
        select(Api).where(
            Api.id == api_id,
            Api.project_id == project_id,
            Api.is_deleted.is_(False),
        )
    ).scalar_one_or_none()
    if not api:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "API not found")
    return api


@router.get("", response_model=ResponseEnvelope)
def list_apis(
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    apis = db.execute(
        select(Api).where(
            Api.project_id == context.project.id,
            Api.is_deleted.is_(False),
        )
    ).scalars().all()
    data = [ApiRead.model_validate(api) for api in apis]
    return success_response(data)


@router.post("", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
def create_api(
    payload: ApiCreate,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    project_id = context.project.id
    method = payload.method.value
    path = payload.path
    version = payload.version

    existing = db.execute(
        select(Api).where(
            Api.project_id == project_id,
            Api.method == method,
            Api.path == path,
            Api.version == version,
            Api.is_deleted.is_(False),
        )
    ).scalar_one_or_none()
    if existing:
        raise http_exception(status.HTTP_409_CONFLICT, ErrorCode.CONFLICT, "API already exists for this method/path/version")

    api = Api(
        project_id=project_id,
        name=payload.name,
        method=method,
        path=path,
        version=version,
        group_name=payload.group_name,
        headers=payload.headers,
        params=payload.params,
        body=payload.body,
        mock_example=payload.mock_example,
    )
    db.add(api)
    db.commit()
    db.refresh(api)

    return success_response(ApiRead.model_validate(api))


@router.get("/{api_id}", response_model=ResponseEnvelope)
def get_api(
    api_id: UUID,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    api = _get_api(db, context.project.id, api_id)
    return success_response(ApiRead.model_validate(api))


@router.patch("/{api_id}", response_model=ResponseEnvelope)
def update_api(
    api_id: UUID,
    payload: ApiUpdate,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    api = _get_api(db, context.project.id, api_id)
    updates = payload.model_dump(exclude_unset=True)

    method = updates.get("method")
    path = updates.get("path")
    version = updates.get("version")

    if method is not None:
        updates["method"] = method.value
    if path is None:
        path = api.path
    if version is None:
        version = api.version
    if method is not None:
        method_value = method.value
    else:
        method_value = api.method

    if (
        method is not None
        or "path" in updates
        or "version" in updates
    ):
        conflict = db.execute(
            select(Api).where(
                Api.project_id == api.project_id,
                Api.method == method_value,
                Api.path == path,
                Api.version == version,
                Api.id != api.id,
                Api.is_deleted.is_(False),
            )
        ).scalar_one_or_none()
        if conflict:
            raise http_exception(status.HTTP_409_CONFLICT, ErrorCode.CONFLICT, "Another API already uses this method/path/version")

    for field, value in updates.items():
        if field == "method" and isinstance(value, str):
            setattr(api, field, value)
        elif hasattr(api, field):
            setattr(api, field, value)

    db.add(api)
    db.commit()
    db.refresh(api)

    return success_response(ApiRead.model_validate(api))


@router.delete("/{api_id}", response_model=ResponseEnvelope)
def delete_api(
    api_id: UUID,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    api = _get_api(db, context.project.id, api_id)
    api.is_deleted = True
    db.add(api)
    db.commit()

    return success_response({"id": api.id, "deleted": True})
