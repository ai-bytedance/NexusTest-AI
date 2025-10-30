from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import get_current_user
from app.core.errors import ErrorCode, http_exception
from app.db.session import get_db
from app.models.user import User
from app.schemas.api_token import ApiTokenCreate, ApiTokenPatchRequest, ApiTokenRead
from app.services.api_tokens import ApiTokenService

router = APIRouter(prefix="/tokens", tags=["tokens"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _serialize_token(token) -> dict:
    schema = ApiTokenRead.model_validate(token)
    return schema.model_dump(mode="json")


@router.get("", response_model=ResponseEnvelope)
def list_tokens(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    service = ApiTokenService(
        db,
        actor=current_user,
        client_ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    tokens = service.list_tokens()
    data = [_serialize_token(token) for token in tokens]
    return success_response(data)


@router.post("", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
def create_token(
    payload: ApiTokenCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    service = ApiTokenService(
        db,
        actor=current_user,
        client_ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    token, secret = service.create_token(
        name=payload.name,
        scopes=payload.scopes,
        project_ids=payload.project_ids,
        expires_at=payload.expires_at,
        rate_limit_policy_id=payload.rate_limit_policy_id,
    )
    data = _serialize_token(token)
    data["token"] = secret
    return success_response(data)


@router.patch("/{token_id}", response_model=ResponseEnvelope)
def update_token(
    token_id: UUID,
    payload: ApiTokenPatchRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    service = ApiTokenService(
        db,
        actor=current_user,
        client_ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    token = service.get_owned_token(token_id)
    if payload.action == "rotate":
        updated, secret = service.rotate_token(token)
        data = _serialize_token(updated)
        data["token"] = secret
        return success_response(data)
    if payload.action == "revoke":
        updated = service.revoke_token(token)
        data = _serialize_token(updated)
        return success_response(data)
    raise http_exception(
        status.HTTP_400_BAD_REQUEST,
        ErrorCode.BAD_REQUEST,
        "Unsupported token action",
    )


@router.delete("/{token_id}", response_model=ResponseEnvelope)
def delete_token(
    token_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    service = ApiTokenService(
        db,
        actor=current_user,
        client_ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    token = service.get_owned_token(token_id)
    service.delete_token(token)
    return success_response({"id": str(token_id), "deleted": True})
