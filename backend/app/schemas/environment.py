from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.common import IdentifierModel, ORMModel


class EnvironmentBase(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    base_url: str | None = Field(default=None, max_length=2048)
    headers: dict[str, Any] = Field(default_factory=dict)
    variables: dict[str, Any] = Field(default_factory=dict)


class EnvironmentCreate(EnvironmentBase):
    secrets: dict[str, str] = Field(default_factory=dict)
    is_default: bool = False


class EnvironmentUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    base_url: str | None = Field(default=None, max_length=2048)
    headers: dict[str, Any] | None = None
    variables: dict[str, Any] | None = None
    secrets: dict[str, str | None] | None = None
    is_default: bool | None = None


class EnvironmentRead(IdentifierModel):
    project_id: UUID
    name: str
    base_url: str | None
    headers: dict[str, Any]
    variables: dict[str, Any]
    secrets: dict[str, bool]
    is_default: bool
    created_by: UUID


class EnvironmentPreview(ORMModel):
    environment: EnvironmentRead


__all__ = [
    "EnvironmentBase",
    "EnvironmentCreate",
    "EnvironmentUpdate",
    "EnvironmentRead",
    "EnvironmentPreview",
]
