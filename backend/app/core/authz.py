from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, Header, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.api_tokens import TokenAuthContext, TokenScope, parse_token, to_uuid_set, verify_token_secret
from app.core.errors import ErrorCode, http_exception
from app.core.scope import resolve_required_scopes
from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_db
from app.logging import bind_log_context, get_logger
from app.models.api_token import ApiToken
from app.models.project import Project
from app.models.project_member import ProjectMember, ProjectRole
from app.models.user import User, UserRole
from app.services.audit_log import record_audit_log
from app.services.rate_limit.engine import enforce_rate_limits

logger = get_logger()

TOKEN_CONTEXT_STATE_KEY = "token_auth_context"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


@dataclass
class ProjectContext:
    project: Project
    membership: ProjectMember


def _clear_token_context(request: Request) -> None:
    if hasattr(request.state, TOKEN_CONTEXT_STATE_KEY):
        delattr(request.state, TOKEN_CONTEXT_STATE_KEY)


def _set_token_context(request: Request, context: TokenAuthContext) -> None:
    setattr(request.state, TOKEN_CONTEXT_STATE_KEY, context)


def get_token_auth_context(request: Request) -> TokenAuthContext | None:
    return getattr(request.state, TOKEN_CONTEXT_STATE_KEY, None)


def _is_pat_token(raw_token: str) -> bool:
    return raw_token.count(".") == 1


def _authenticate_jwt(raw_token: str, db: Session) -> User:
    try:
        payload = decode_access_token(raw_token)
    except InvalidTokenError:
        raise http_exception(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_TOKEN_INVALID,
            "Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    subject = payload.get("sub")
    if not subject:
        raise http_exception(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_TOKEN_INVALID,
            "Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = uuid.UUID(subject)
    except ValueError:
        raise http_exception(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_TOKEN_INVALID,
            "Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user = db.get(User, user_id)
    if not user or user.is_deleted:
        raise http_exception(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_TOKEN_INVALID,
            "Authentication credentials are no longer valid",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def _authenticate_api_token(request: Request, raw_token: str, db: Session) -> User:
    try:
        prefix, secret = parse_token(raw_token)
    except ValueError:
        raise http_exception(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_TOKEN_INVALID,
            "Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    stmt = select(ApiToken).where(ApiToken.token_prefix == prefix).limit(1)
    api_token = db.execute(stmt).scalar_one_or_none()
    if api_token is None:
        raise http_exception(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_TOKEN_INVALID,
            "Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_token_secret(secret, api_token.token_hash):
        raise http_exception(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_TOKEN_INVALID,
            "Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    now = datetime.now(timezone.utc)
    if api_token.revoked_at is not None:
        raise http_exception(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_TOKEN_INVALID,
            "Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if api_token.expires_at is not None and now >= api_token.expires_at:
        raise http_exception(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_TOKEN_INVALID,
            "Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, api_token.user_id)
    if user is None or user.is_deleted:
        raise http_exception(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_TOKEN_INVALID,
            "Authentication credentials are no longer valid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scopes = frozenset(str(scope) for scope in api_token.scopes or [])
    project_ids = to_uuid_set(tuple(api_token.project_ids or []))
    context = TokenAuthContext(
        token_id=api_token.id,
        token_prefix=api_token.token_prefix,
        scopes=scopes,
        project_ids=project_ids,
        expires_at=api_token.expires_at,
        rate_limit_policy_id=api_token.rate_limit_policy_id,
    )
    _set_token_context(request, context)
    setattr(request.state, "authenticated_via", "api_token")
    bind_log_context(token_id=str(api_token.id))

    api_token.last_used_at = now
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    record_audit_log(
        db,
        actor=user,
        action="token.used",
        resource_type="api_token",
        resource_id=str(api_token.id),
        project_id=None,
        metadata={
            "path": request.url.path,
            "method": request.method,
            "project_ids": [str(project_id) for project_id in project_ids],
        },
        ip=client_ip,
        user_agent=user_agent,
    )
    db.add(api_token)
    db.commit()
    db.refresh(api_token)
    return user


def _enforce_token_scopes(request: Request, token_context: TokenAuthContext | None) -> None:
    if token_context is None:
        return
    required_scopes, allow_pat = resolve_required_scopes(request)
    if not allow_pat:
        raise http_exception(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.NO_PERMISSION,
            "Personal access tokens are not allowed to call this endpoint",
        )
    if not required_scopes:
        return
    if TokenScope.ADMIN.value in token_context.scopes:
        return
    if token_context.scopes.intersection(required_scopes):
        return
    raise http_exception(
        status.HTTP_403_FORBIDDEN,
        ErrorCode.NO_PERMISSION,
        "Personal access token is missing required scope",
        data={"required_scopes": sorted(required_scopes)},
    )


def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    _clear_token_context(request)
    if not token:
        raise http_exception(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.NOT_AUTHENTICATED,
            "Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if _is_pat_token(token):
        user = _authenticate_api_token(request, token, db)
        _enforce_token_scopes(request, get_token_auth_context(request))
        return user

    user = _authenticate_jwt(token, db)
    setattr(request.state, "authenticated_via", "jwt")
    return user


def _project_statement(project_id: Optional[uuid.UUID], project_key: Optional[str]) -> Select[tuple[Project]]:
    stmt: Select[tuple[Project]] = select(Project).where(Project.is_deleted.is_(False))
    if project_id:
        stmt = stmt.where(Project.id == project_id)
    elif project_key:
        stmt = stmt.where(Project.key == project_key)
    return stmt


def _assert_token_project_scope(request: Request, project_id: uuid.UUID) -> None:
    context = get_token_auth_context(request)
    if context is None:
        return
    if context.project_ids and project_id not in context.project_ids:
        raise http_exception(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.NO_PERMISSION,
            "Token is not authorized for this project",
        )


def get_project_context(
    request: Request,
    project_id: Optional[uuid.UUID] = None,
    project_key: Optional[str] = Header(default=None, alias="X-Project-Key"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectContext:
    if not project_id and not project_key:
        raise http_exception(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.BAD_REQUEST,
            "Project context is required",
        )

    stmt = _project_statement(project_id, project_key)
    project = db.execute(stmt).scalar_one_or_none()
    if not project:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Project not found")

    _assert_token_project_scope(request, project.id)

    membership_stmt = select(ProjectMember).where(
        ProjectMember.project_id == project.id,
        ProjectMember.user_id == current_user.id,
        ProjectMember.is_deleted.is_(False),
    )
    membership = db.execute(membership_stmt).scalar_one_or_none()
    if not membership:
        raise http_exception(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.NO_PERMISSION,
            "You do not have access to this project",
        )

    bind_log_context(project_id=str(project.id))
    enforce_rate_limits(
        db,
        request=request,
        auth_context=get_token_auth_context(request),
        project=project,
    )

    return ProjectContext(project=project, membership=membership)


def require_project_member(context: ProjectContext = Depends(get_project_context)) -> ProjectContext:
    return context


def require_project_admin(context: ProjectContext = Depends(get_project_context)) -> ProjectContext:
    if context.membership.role != ProjectRole.ADMIN:
        raise http_exception(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.NO_PERMISSION,
            "Project admin privileges are required",
        )
    return context


def require_system_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise http_exception(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.NO_PERMISSION,
            "Administrator privileges are required",
        )
    return current_user
