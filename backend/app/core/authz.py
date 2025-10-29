from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode, http_exception
from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_db
from app.logging import bind_log_context
from app.models.project import Project
from app.models.project_member import ProjectMember, ProjectRole
from app.models.user import User


@dataclass
class ProjectContext:
    project: Project
    membership: ProjectMember


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(token: Optional[str] = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    if not token:
        raise http_exception(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.NOT_AUTHENTICATED,
            "Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
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


def _project_statement(project_id: Optional[uuid.UUID], project_key: Optional[str]) -> Select[tuple[Project]]:
    stmt: Select[tuple[Project]] = select(Project).where(Project.is_deleted.is_(False))
    if project_id:
        stmt = stmt.where(Project.id == project_id)
    elif project_key:
        stmt = stmt.where(Project.key == project_key)
    return stmt


def get_project_context(
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
