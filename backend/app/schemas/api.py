from __future__ import annotations

import enum
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.common import IdentifierModel, ORMModel


class HTTPMethod(str, enum.Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class ApiBase(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    method: HTTPMethod
    path: str = Field(min_length=1, max_length=512)
    version: str = Field(default="v1", min_length=1, max_length=32)
    group_name: str | None = Field(default=None, max_length=255)
    headers: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    body: dict[str, Any] = Field(default_factory=dict)
    mock_example: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("path")
    @classmethod
    def ensure_leading_slash(cls, value: str) -> str:
        if not value.startswith("/"):
            return f"/{value}"
        return value


class ApiCreate(ApiBase):
    pass


class ApiUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    method: HTTPMethod | None = None
    path: str | None = Field(default=None, min_length=1, max_length=512)
    version: str | None = Field(default=None, min_length=1, max_length=32)
    group_name: str | None = Field(default=None, max_length=255)
    headers: dict[str, Any] | None = None
    params: dict[str, Any] | None = None
    body: dict[str, Any] | None = None
    mock_example: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("path")
    @classmethod
    def ensure_optional_leading_slash(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.startswith("/"):
            return f"/{value}"
        return value


class ApiRead(IdentifierModel):
    project_id: UUID
    name: str
    method: HTTPMethod
    path: str
    normalized_path: str
    version: str
    group_name: str | None
    headers: dict[str, Any]
    params: dict[str, Any]
    body: dict[str, Any]
    mock_example: dict[str, Any]
    metadata: dict[str, Any]
    import_source_id: UUID | None
