from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from app.models.execution_routing import AgentSelectionPolicy
from app.schemas.common import IdentifierModel, ORMModel


class TestSuiteBase(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    steps: list[Any] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)


class TestSuiteCreate(TestSuiteBase):
    queue_id: UUID | None = None
    agent_selection_policy: AgentSelectionPolicy = AgentSelectionPolicy.ROUND_ROBIN
    agent_tags: list[str] = Field(default_factory=list)


class TestSuiteUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    steps: list[Any] | None = None
    variables: dict[str, Any] | None = None
    queue_id: UUID | None = None
    agent_selection_policy: AgentSelectionPolicy | None = None
    agent_tags: list[str] | None = None


class TestSuiteRead(IdentifierModel):
    project_id: UUID
    name: str
    description: str | None
    steps: list[Any]
    variables: dict[str, Any]
    queue_id: UUID | None
    agent_selection_policy: AgentSelectionPolicy
    agent_tags: list[str]
    created_by: UUID
