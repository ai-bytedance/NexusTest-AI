from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.models.execution_routing import AgentSelectionPolicy
from app.schemas.assertions import AssertionDefinition
from app.schemas.common import IdentifierModel, ORMModel


class TestCaseBase(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    inputs: dict[str, Any] = Field(default_factory=dict)
    expected: dict[str, Any] = Field(default_factory=dict)
    assertions: list[AssertionDefinition] = Field(default_factory=list)
    enabled: bool = True


class TestCaseCreate(TestCaseBase):
    api_id: UUID
    environment_id: UUID | None = None
    dataset_id: UUID | None = None
    queue_id: UUID | None = None
    agent_selection_policy: AgentSelectionPolicy = AgentSelectionPolicy.ROUND_ROBIN
    agent_tags: list[str] = Field(default_factory=list)
    param_mapping: dict[str, Any] = Field(default_factory=dict)


class TestCaseUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    inputs: dict[str, Any] | None = None
    expected: dict[str, Any] | None = None
    assertions: list[AssertionDefinition] | None = None
    enabled: bool | None = None
    environment_id: UUID | None = None
    dataset_id: UUID | None = None
    queue_id: UUID | None = None
    agent_selection_policy: AgentSelectionPolicy | None = None
    agent_tags: list[str] | None = None
    param_mapping: dict[str, Any] | None = None


class TestCaseRead(IdentifierModel):
    project_id: UUID
    api_id: UUID
    name: str
    inputs: dict[str, Any]
    expected: dict[str, Any]
    assertions: list[dict[str, Any]]
    environment_id: UUID | None
    dataset_id: UUID | None
    queue_id: UUID | None
    agent_selection_policy: AgentSelectionPolicy
    agent_tags: list[str]
    param_mapping: dict[str, Any]
    enabled: bool
    created_by: UUID


class TestCaseAssertionUpdateItem(ORMModel):
    index: int | None = Field(default=None, ge=0)
    assertion: AssertionDefinition


class TestCaseAssertionsUpdateRequest(ORMModel):
    operation: Literal["replace", "patch"] = Field("replace")
    items: list[TestCaseAssertionUpdateItem] = Field(default_factory=list)

    @field_validator("items", mode="before")
    @classmethod
    def _coerce_items(cls, value: Any) -> list[TestCaseAssertionUpdateItem] | Any:
        if value is None:
            return []
        return value

    @model_validator(mode="after")
    def _validate_patch(self) -> "TestCaseAssertionsUpdateRequest":
        if self.operation == "patch":
            for item in self.items:
                if item.index is None:
                    raise ValueError("Patch operations require an index for each assertion")
        return self

