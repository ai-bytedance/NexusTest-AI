from __future__ import annotations

from typing import Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import (
    ProjectContext,
    get_current_user,
    require_project_admin,
    require_project_member,
)
from app.core.errors import ErrorCode, http_exception
from app.db.session import get_db
from app.models.project import Project
from app.models.project_member import ProjectMember, ProjectRole
from app.models.user import User
from app.schemas.project import (
    ProjectCreate,
    ProjectMemberCreate,
    ProjectMemberDeleteResponse,
    ProjectMemberRead,
    ProjectMemberUser,
    ProjectRead,
    ProjectUpdate,
    ProjectWithMembers,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def _normalize_email_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    candidates: list[str] = []
    if isinstance(raw, str):
        candidates = [item.strip() for item in raw.split(",")]
    elif isinstance(raw, (list, tuple, set)):
        for item in raw:
            if isinstance(item, str):
                candidates.append(item.strip())
    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        email = candidate.lower()
        if not email or email in seen:
            continue
        seen.add(email)
        normalized.append(email)
    return normalized


def _normalize_notification_settings(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"email": {"defaults": {"to": [], "cc": [], "bcc": []}}}

    email_settings = value.get("email") if isinstance(value.get("email"), dict) else {}
    defaults_raw = email_settings.get("defaults") if isinstance(email_settings, dict) else {}
    if not isinstance(defaults_raw, dict):
        defaults_raw = {}

    defaults = {
        "to": _normalize_email_list(defaults_raw.get("to")),
        "cc": _normalize_email_list(defaults_raw.get("cc")),
        "bcc": _normalize_email_list(defaults_raw.get("bcc")),
    }

    dynamic_raw = email_settings.get("dynamic") if isinstance(email_settings, dict) else {}
    dynamic_flags = {
        "owners": bool(dynamic_raw.get("owners")) if isinstance(dynamic_raw, dict) else False,
        "admins": bool(dynamic_raw.get("admins")) if isinstance(dynamic_raw, dict) else False,
        "members": bool(dynamic_raw.get("members")) if isinstance(dynamic_raw, dict) else False,
    }

    reply_to_raw = email_settings.get("reply_to") if isinstance(email_settings, dict) else None
    reply_to = reply_to_raw.strip().lower() if isinstance(reply_to_raw, str) and reply_to_raw.strip() else None

    email_result: dict[str, Any] = {"defaults": defaults}
    if any(dynamic_flags.values()):
        email_result["dynamic"] = dynamic_flags
    if reply_to:
        email_result["reply_to"] = reply_to

    return {"email": email_result}


def _load_project_with_members(db: Session, project_id: UUID) -> Project:
    stmt = (
        select(Project)
        .where(Project.id == project_id, Project.is_deleted.is_(False))
        .options(selectinload(Project.members).selectinload(ProjectMember.user))
    )
    project = db.execute(stmt).unique().scalar_one_or_none()
    if not project:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Project not found")
    return project


def _serialize_member(member: ProjectMember) -> ProjectMemberRead:
    if member.user is None:
        raise http_exception(status.HTTP_500_INTERNAL_SERVER_ERROR, ErrorCode.BAD_REQUEST, "Member user not loaded")
    return ProjectMemberRead(
        id=member.id,
        created_at=member.created_at,
        updated_at=member.updated_at,
        project_id=member.project_id,
        user_id=member.user_id,
        role=member.role,
        user=ProjectMemberUser(id=member.user.id, email=member.user.email),
    )


def _serialize_project(project: Project, include_members: bool = False) -> ProjectRead | ProjectWithMembers:
    settings_payload = _normalize_notification_settings(project.notification_settings)
    if not include_members:
        return ProjectRead(
            id=project.id,
            created_at=project.created_at,
            updated_at=project.updated_at,
            name=project.name,
            key=project.key,
            description=project.description,
            created_by=project.created_by,
            notification_settings=settings_payload,
        )

    active_members = [member for member in project.members if not member.is_deleted]
    members_payload: List[ProjectMemberRead] = [_serialize_member(member) for member in active_members]
    return ProjectWithMembers(
        id=project.id,
        created_at=project.created_at,
        updated_at=project.updated_at,
        name=project.name,
        key=project.key,
        description=project.description,
        created_by=project.created_by,
        notification_settings=settings_payload,
        members=members_payload,
    )


@router.post("", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    normalized_key = payload.key

    existing_key = db.execute(select(Project).where(Project.key == normalized_key)).scalar_one_or_none()
    if existing_key:
        raise http_exception(status.HTTP_409_CONFLICT, ErrorCode.CONFLICT, "Project key already exists")

    existing_name = db.execute(select(Project).where(Project.name == payload.name)).scalar_one_or_none()
    if existing_name:
        raise http_exception(status.HTTP_409_CONFLICT, ErrorCode.CONFLICT, "Project name already exists")

    project = Project(
        name=payload.name,
        key=normalized_key,
        description=payload.description,
        created_by=current_user.id,
    )
    membership = ProjectMember(project=project, user=current_user, role=ProjectRole.ADMIN)

    db.add(project)
    db.add(membership)
    db.commit()

    project = _load_project_with_members(db, project.id)
    response = _serialize_project(project, include_members=True)
    return success_response(response)


@router.get("", response_model=ResponseEnvelope)
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    stmt = (
        select(Project)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(
            ProjectMember.user_id == current_user.id,
            ProjectMember.is_deleted.is_(False),
            Project.is_deleted.is_(False),
        )
        .order_by(Project.created_at)
    )
    projects = db.execute(stmt).scalars().unique().all()
    data = [ProjectRead.model_validate(project) for project in projects]
    return success_response(data)


@router.get("/{project_id}", response_model=ResponseEnvelope)
def get_project(
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    project = _load_project_with_members(db, context.project.id)
    response = _serialize_project(project, include_members=True)
    return success_response(response)


@router.patch("/{project_id}", response_model=ResponseEnvelope)
def update_project(
    payload: ProjectUpdate,
    context: ProjectContext = Depends(require_project_admin),
    db: Session = Depends(get_db),
) -> dict:
    project = context.project
    updates = payload.model_dump(exclude_unset=True)

    if "name" in updates and updates["name"] != project.name:
        conflict = db.execute(
            select(Project).where(Project.name == updates["name"], Project.id != project.id)
        ).scalar_one_or_none()
        if conflict:
            raise http_exception(status.HTTP_409_CONFLICT, ErrorCode.CONFLICT, "Project name already exists")
        project.name = updates["name"]

    if "key" in updates and updates["key"] != project.key:
        conflict = db.execute(
            select(Project).where(Project.key == updates["key"], Project.id != project.id)
        ).scalar_one_or_none()
        if conflict:
            raise http_exception(status.HTTP_409_CONFLICT, ErrorCode.CONFLICT, "Project key already exists")
        project.key = updates["key"]

    if "description" in updates:
        project.description = updates["description"]

    if "notification_settings" in updates:
        project.notification_settings = _normalize_notification_settings(updates["notification_settings"])

    db.add(project)
    db.commit()
    db.refresh(project)

    response = _serialize_project(project)
    return success_response(response)


@router.delete("/{project_id}", response_model=ResponseEnvelope, status_code=status.HTTP_200_OK)
def delete_project(
    context: ProjectContext = Depends(require_project_admin),
    db: Session = Depends(get_db),
) -> dict:
    project = context.project
    if project.is_deleted:
        return success_response({"id": project.id, "deleted": True})

    project.is_deleted = True
    for member in project.members:
        member.is_deleted = True
        db.add(member)
    db.add(project)
    db.commit()

    return success_response({"id": project.id, "deleted": True})


@router.post("/{project_id}/members", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
def add_project_member(
    payload: ProjectMemberCreate,
    context: ProjectContext = Depends(require_project_admin),
    db: Session = Depends(get_db),
) -> dict:
    project = context.project

    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if not user or user.is_deleted:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "User not found")

    membership = db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user.id,
        )
    ).scalar_one_or_none()

    if membership and not membership.is_deleted:
        raise http_exception(status.HTTP_409_CONFLICT, ErrorCode.CONFLICT, "User is already a project member")

    if membership and membership.is_deleted:
        membership.is_deleted = False
        membership.role = payload.role
    else:
        membership = ProjectMember(project=project, user=user, role=payload.role)
        db.add(membership)

    db.commit()
    db.refresh(membership)
    db.refresh(membership, attribute_names=["user"])

    response = _serialize_member(membership)
    return success_response(response)


@router.delete("/{project_id}/members/{user_id}", response_model=ResponseEnvelope, status_code=status.HTTP_200_OK)
def remove_project_member(
    user_id: UUID,
    context: ProjectContext = Depends(require_project_admin),
    db: Session = Depends(get_db),
) -> dict:
    project = context.project

    membership = db.execute(
        select(ProjectMember)
        .where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user_id,
            ProjectMember.is_deleted.is_(False),
        )
        .options(selectinload(ProjectMember.user))
    ).scalar_one_or_none()

    if not membership:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Member not found")

    admin_count = db.execute(
        select(func.count())
        .select_from(ProjectMember)
        .where(
            ProjectMember.project_id == project.id,
            ProjectMember.role == ProjectRole.ADMIN,
            ProjectMember.is_deleted.is_(False),
        )
    ).scalar_one()

    if membership.user_id == context.membership.user_id and admin_count <= 1:
        raise http_exception(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.BAD_REQUEST,
            "Cannot remove the last project admin",
        )

    membership.is_deleted = True
    db.add(membership)
    db.commit()

    return success_response(ProjectMemberDeleteResponse(removed_user_id=user_id))
