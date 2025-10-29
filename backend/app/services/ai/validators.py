from __future__ import annotations

from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StepDefinition(BaseModel):
    """Represents an individual test step instruction."""

    action: str
    note: str | None = None
    method: str | None = None
    path: str | None = None
    payload: dict[str, Any] | list[Any] | None = None
    headers: dict[str, Any] | None = None
    params: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")


class AssertionDefinition(BaseModel):
    """Represents a single assertion definition."""

    name: str
    operator: str
    expected: Any | None = None
    actual: Any | None = None
    path: str | None = None
    tolerance: float | None = None
    comparator: str | None = None

    model_config = ConfigDict(extra="allow")


class TestCaseDefinition(BaseModel):
    """Represents a generated test case."""

    name: str
    description: str
    steps: list[StepDefinition]
    assertions: list[AssertionDefinition]
    tags: list[str] | None = None
    priority: str | None = None

    model_config = ConfigDict(extra="allow")

    @field_validator("steps")
    @classmethod
    def validate_steps(cls, steps: Sequence[StepDefinition]) -> Sequence[StepDefinition]:
        if not steps:
            raise ValueError("Generated test cases must include at least one step")
        return steps

    @field_validator("assertions")
    @classmethod
    def validate_assertions(cls, assertions: Sequence[AssertionDefinition]) -> Sequence[AssertionDefinition]:
        if not assertions:
            raise ValueError("Generated test cases must include at least one assertion")
        return assertions


class GenerateCasesResult(BaseModel):
    cases: list[TestCaseDefinition] = Field(..., description="List of generated test cases")

    model_config = ConfigDict(extra="ignore")

    @field_validator("cases")
    @classmethod
    def validate_cases(cls, cases: Sequence[TestCaseDefinition]) -> Sequence[TestCaseDefinition]:
        if not cases:
            raise ValueError("At least one test case must be returned")
        return cases


class GenerateAssertionsResult(BaseModel):
    assertions: list[AssertionDefinition] = Field(..., description="List of generated assertions")

    model_config = ConfigDict(extra="ignore")

    @field_validator("assertions")
    @classmethod
    def ensure_assertions(cls, assertions: Sequence[AssertionDefinition]) -> Sequence[AssertionDefinition]:
        if not assertions:
            raise ValueError("At least one assertion must be returned")
        return assertions


class GenerateMockDataResult(BaseModel):
    data: dict[str, Any] | list[Any]

    model_config = ConfigDict(extra="ignore")

    @field_validator("data")
    @classmethod
    def validate_data(cls, value: dict[str, Any] | list[Any]) -> dict[str, Any] | list[Any]:
        if isinstance(value, (dict, list)):
            return value
        raise ValueError("Mock data must be an object or array")


class SummarizeReportResult(BaseModel):
    markdown: str

    model_config = ConfigDict(extra="ignore")

    @field_validator("markdown")
    @classmethod
    def validate_markdown(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Markdown summary must not be empty")
        return value.strip()


def validate_generate_cases(payload: dict[str, Any]) -> dict[str, Any]:
    return GenerateCasesResult.model_validate(payload).model_dump(mode="json")


def validate_generate_assertions(payload: dict[str, Any]) -> dict[str, Any]:
    return GenerateAssertionsResult.model_validate(payload).model_dump(mode="json")


def validate_generate_mock_data(payload: dict[str, Any]) -> dict[str, Any]:
    return GenerateMockDataResult.model_validate(payload).model_dump(mode="json")


def validate_summarize_report(payload: dict[str, Any]) -> dict[str, Any]:
    return SummarizeReportResult.model_validate(payload).model_dump(mode="json")


def generate_cases_json_schema() -> dict[str, Any]:
    return GenerateCasesResult.model_json_schema()


def generate_assertions_json_schema() -> dict[str, Any]:
    return GenerateAssertionsResult.model_json_schema()


def generate_mock_data_json_schema() -> dict[str, Any]:
    return GenerateMockDataResult.model_json_schema()


def summarize_report_json_schema() -> dict[str, Any]:
    return SummarizeReportResult.model_json_schema()
