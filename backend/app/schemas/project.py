from __future__ import annotations

import re
from typing import List
from uuid import UUID

from pydantic import EmailStr, Field, field_validator

from app.models.project_member import ProjectRole
from app.schemas.common import IdentifierModel, ORMModel

PROJECT_KEY_PATTERN = re.compile(r"^[A-Z0-9_]{3,32}$")


class ProjectBase(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    key: str = Field(min_length=3, max_length=32)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        normalized = value.upper()
        if not PROJECT_KEY_PATTERN.match(normalized):
            raise ValueError("Project key must be 3-32 characters (A-Z, 0-9, underscore)")
        return normalized


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    key: str | None = Field(default=None, min_length=3, max_length=32)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("key")
    @classmethod
    def validate_optional_key(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.upper()
        if not PROJECT_KEY_PATTERN.match(normalized):
            raise ValueError("Project key must be 3-32 characters (A-Z, 0-9, underscore)")
        return normalized


class ProjectRead(IdentifierModel):
    name: str
    key: str
    description: str | None
    created_by: UUID


class ProjectMemberUser(ORMModel):
    id: UUID
    email: EmailStr


class ProjectMemberRead(IdentifierModel):
    project_id: UUID
    user_id: UUID
    role: ProjectRole
    user: ProjectMemberUser


class ProjectWithMembers(ProjectRead):
    members: List[ProjectMemberRead]


class ProjectMemberCreate(ORMModel):
    email: EmailStr
    role: ProjectRole = Field(default=ProjectRole.MEMBER)


class ProjectMemberDeleteResponse(ORMModel):
    removed_user_id: UUID
