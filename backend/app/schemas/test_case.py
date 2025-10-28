from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.common import IdentifierModel, ORMModel


class TestCaseBase(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    inputs: dict[str, Any] = Field(default_factory=dict)
    expected: dict[str, Any] = Field(default_factory=dict)
    assertions: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class TestCaseCreate(TestCaseBase):
    api_id: UUID


class TestCaseUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    inputs: dict[str, Any] | None = None
    expected: dict[str, Any] | None = None
    assertions: dict[str, Any] | None = None
    enabled: bool | None = None


class TestCaseRead(IdentifierModel):
    project_id: UUID
    api_id: UUID
    name: str
    inputs: dict[str, Any]
    expected: dict[str, Any]
    assertions: dict[str, Any]
    enabled: bool
    created_by: UUID
