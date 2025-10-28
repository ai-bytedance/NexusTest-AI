from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.common import IdentifierModel, ORMModel


class TestSuiteBase(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    steps: list[Any] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)


class TestSuiteCreate(TestSuiteBase):
    pass


class TestSuiteUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    steps: list[Any] | None = None
    variables: dict[str, Any] | None = None


class TestSuiteRead(IdentifierModel):
    project_id: UUID
    name: str
    description: str | None
    steps: list[Any]
    variables: dict[str, Any]
    created_by: UUID
