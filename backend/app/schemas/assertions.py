from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AssertionOperator = Literal[
    "status_code",
    "equals",
    "not_equals",
    "contains",
    "regex",
    "jsonpath_equals",
    "jsonpath_contains",
    "length",
    "gt",
    "lt",
]


class AssertionBase(BaseModel):
    """Base schema for assertion definitions."""

    operator: AssertionOperator
    name: str | None = Field(None, max_length=128)
    message: str | None = Field(
        default=None,
        description="Custom message to display when the assertion fails.",
    )
    enabled: bool = Field(default=True, description="Whether the assertion is active.")

    model_config = ConfigDict(extra="ignore")


class StatusCodeAssertion(AssertionBase):
    operator: Literal["status_code"]
    expected: int = Field(..., description="Expected HTTP status code.")

    @field_validator("expected")
    @classmethod
    def _validate_expected(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("status_code assertions require an integer expected value")
        if value < 100 or value > 599:
            raise ValueError("status_code assertions must be between 100 and 599")
        return value


class BinaryValueAssertion(AssertionBase):
    actual: Any = Field(..., description="Left-hand value for the assertion.")
    expected: Any = Field(..., description="Right-hand value for the assertion.")


class EqualsAssertion(BinaryValueAssertion):
    operator: Literal["equals"]


class NotEqualsAssertion(BinaryValueAssertion):
    operator: Literal["not_equals"]


class ContainsAssertion(BinaryValueAssertion):
    operator: Literal["contains"]


class RegexAssertion(BinaryValueAssertion):
    operator: Literal["regex"]

    @field_validator("expected")
    @classmethod
    def _validate_pattern(cls, value: Any) -> Any:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("regex assertions require a non-empty pattern string")
        return value


class JsonPathAssertion(AssertionBase):
    path: str = Field(..., description="JSONPath expression to evaluate against the response JSON body.")
    expected: Any = Field(..., description="Expected value for the JSONPath lookup.")

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("JSONPath assertions require a non-empty path expression")
        return value


class JsonPathEqualsAssertion(JsonPathAssertion):
    operator: Literal["jsonpath_equals"]


class JsonPathContainsAssertion(JsonPathAssertion):
    operator: Literal["jsonpath_contains"]


class LengthAssertion(AssertionBase):
    operator: Literal["length"]
    actual: Any = Field(..., description="Collection or string whose length will be compared.")
    expected: int = Field(..., description="Expected length value.")

    @field_validator("expected")
    @classmethod
    def _validate_expected(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("length assertions require an integer expected value")
        if value < 0:
            raise ValueError("length assertions require a non-negative expected value")
        return value


class GreaterThanAssertion(BinaryValueAssertion):
    operator: Literal["gt"]

    @field_validator("expected")
    @classmethod
    def _validate_expected_numeric(cls, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("gt assertions require a numeric expected value")
        return value


class LessThanAssertion(BinaryValueAssertion):
    operator: Literal["lt"]

    @field_validator("expected")
    @classmethod
    def _validate_expected_numeric(cls, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("lt assertions require a numeric expected value")
        return value


AssertionDefinition = Annotated[
    StatusCodeAssertion
    | EqualsAssertion
    | NotEqualsAssertion
    | ContainsAssertion
    | RegexAssertion
    | JsonPathEqualsAssertion
    | JsonPathContainsAssertion
    | LengthAssertion
    | GreaterThanAssertion
    | LessThanAssertion,
    Field(discriminator="operator"),
]


class AssertionCollection(BaseModel):
    items: list[AssertionDefinition] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class JsonDiffEntry(BaseModel):
    path: str = Field(..., description="JSON pointer identifying where the difference occurred.")
    change: Literal["added", "removed", "changed", "type"] = Field(
        ..., description="Type of difference that was detected."
    )
    expected: Any | None = Field(default=None)
    actual: Any | None = Field(default=None)

    model_config = ConfigDict(extra="ignore")


class AssertionResultRead(BaseModel):
    name: str | None = None
    operator: str
    passed: bool
    actual: Any | None = None
    expected: Any | None = None
    message: str | None = None
    path: str | None = None
    diff: str | None = None
    diff_entries: list[JsonDiffEntry] | None = None

    model_config = ConfigDict(extra="ignore")


class JsonPathTestRequest(BaseModel):
    json: Any = Field(default_factory=dict)
    path: str = Field(..., description="JSONPath expression to evaluate", min_length=1)

    model_config = ConfigDict(extra="ignore")


class JsonPathTestResponse(BaseModel):
    matches: list[Any] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class AssertionPreviewRequest(BaseModel):
    assertion: AssertionDefinition
    response_json: Any | None = None
    status_code: int | None = None
    headers: dict[str, Any] | None = None
    body: str | None = None

    model_config = ConfigDict(extra="ignore")


class AssertionPreviewResponse(BaseModel):
    passed: bool
    result: AssertionResultRead | None = None

    model_config = ConfigDict(extra="ignore")


__all__ = [
    "AssertionDefinition",
    "AssertionOperator",
    "AssertionCollection",
    "JsonDiffEntry",
    "AssertionResultRead",
    "JsonPathTestRequest",
    "JsonPathTestResponse",
    "AssertionPreviewRequest",
    "AssertionPreviewResponse",
]
