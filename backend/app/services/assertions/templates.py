from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Sequence

from pydantic import ValidationError

from app.schemas.assertions import AssertionDefinition, AssertionOperator

FieldKind = Literal["number", "string", "json", "expression", "path", "boolean"]
TemplateCategory = Literal["basic", "jsonpath", "regex", "advanced"]


@dataclass(frozen=True)
class AssertionFieldTemplate:
    """Describes a single configurable input within an assertion template."""

    name: str
    label: str
    kind: FieldKind
    required: bool = True
    description: str | None = None
    placeholder: str | None = None
    default: Any | None = None
    examples: Sequence[Any] = field(default_factory=tuple)


@dataclass(frozen=True)
class AssertionTemplate:
    """Metadata describing how a visual builder should render an assertion."""

    operator: AssertionOperator
    category: TemplateCategory
    label: str
    description: str
    fields: Sequence[AssertionFieldTemplate]
    defaults: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operator": self.operator,
            "category": self.category,
            "label": self.label,
            "description": self.description,
            "defaults": self.defaults,
            "fields": [field.__dict__ for field in self.fields],
        }


COMMON_ASSERTION_TEMPLATES: tuple[AssertionTemplate, ...] = (
    AssertionTemplate(
        operator="status_code",
        category="basic",
        label="Status code equals",
        description="Verify the HTTP status code matches the expected value.",
        defaults={"expected": 200},
        fields=(
            AssertionFieldTemplate(
                name="expected",
                label="Expected status",
                kind="number",
                description="Expected HTTP status code (100-599).",
                default=200,
                examples=(200, 201, 204, 400, 500),
            ),
        ),
    ),
    AssertionTemplate(
        operator="equals",
        category="basic",
        label="Equals",
        description="Check that two values are strictly equal.",
        fields=(
            AssertionFieldTemplate(
                name="actual",
                label="Actual value",
                kind="expression",
                description="Expression or path to resolve the actual value (e.g. {{response.json.data}}).",
                placeholder="{{response.json.data}}",
            ),
            AssertionFieldTemplate(
                name="expected",
                label="Expected value",
                kind="json",
                description="Expected JSON/value for comparison.",
            ),
        ),
    ),
    AssertionTemplate(
        operator="not_equals",
        category="basic",
        label="Not equals",
        description="Ensure two values are different.",
        fields=(
            AssertionFieldTemplate(
                name="actual",
                label="Actual value",
                kind="expression",
                placeholder="{{response.json.data}}",
            ),
            AssertionFieldTemplate(
                name="expected",
                label="Unexpected value",
                kind="json",
            ),
        ),
    ),
    AssertionTemplate(
        operator="contains",
        category="basic",
        label="Contains",
        description="Assert that the actual value contains the expected fragment.",
        fields=(
            AssertionFieldTemplate(
                name="actual",
                label="Actual value",
                kind="expression",
                placeholder="{{response.body}}",
            ),
            AssertionFieldTemplate(
                name="expected",
                label="Expected fragment",
                kind="string",
                description="Substring or element expected to be present in the actual value.",
            ),
        ),
    ),
    AssertionTemplate(
        operator="regex",
        category="regex",
        label="Regex match",
        description="Validate that the actual value matches a regular expression.",
        fields=(
            AssertionFieldTemplate(
                name="actual",
                label="Actual value",
                kind="expression",
                placeholder="{{response.body}}",
            ),
            AssertionFieldTemplate(
                name="expected",
                label="Pattern",
                kind="string",
                description="Regular expression pattern (Python syntax).",
                placeholder=r"^SUCCESS$",
            ),
        ),
    ),
    AssertionTemplate(
        operator="jsonpath_equals",
        category="jsonpath",
        label="JSONPath equals",
        description="Evaluate a JSONPath expression and compare the result to an expected value.",
        fields=(
            AssertionFieldTemplate(
                name="path",
                label="JSONPath",
                kind="path",
                description="JSONPath expression resolved against the response JSON body.",
                placeholder="$.data.id",
            ),
            AssertionFieldTemplate(
                name="expected",
                label="Expected value",
                kind="json",
            ),
        ),
    ),
    AssertionTemplate(
        operator="jsonpath_contains",
        category="jsonpath",
        label="JSONPath contains",
        description="Ensure the JSONPath result contains the expected value.",
        fields=(
            AssertionFieldTemplate(
                name="path",
                label="JSONPath",
                kind="path",
                placeholder="$.items[*].id",
            ),
            AssertionFieldTemplate(
                name="expected",
                label="Expected fragment",
                kind="json",
            ),
        ),
    ),
    AssertionTemplate(
        operator="length",
        category="advanced",
        label="Length equals",
        description="Compare the length of a list/string/dict against an expected value.",
        defaults={"expected": 1},
        fields=(
            AssertionFieldTemplate(
                name="actual",
                label="Collection",
                kind="expression",
                placeholder="{{response.json.items}}",
                description="Expression resolving to the collection whose length will be checked.",
            ),
            AssertionFieldTemplate(
                name="expected",
                label="Expected length",
                kind="number",
                default=1,
            ),
        ),
    ),
    AssertionTemplate(
        operator="gt",
        category="advanced",
        label="Greater than",
        description="Ensure the actual numeric value is greater than the expected value.",
        fields=(
            AssertionFieldTemplate(
                name="actual",
                label="Actual value",
                kind="expression",
                placeholder="{{response.json.duration_ms}}",
            ),
            AssertionFieldTemplate(
                name="expected",
                label="Threshold",
                kind="number",
                placeholder="0",
            ),
        ),
    ),
    AssertionTemplate(
        operator="lt",
        category="advanced",
        label="Less than",
        description="Ensure the actual numeric value is less than the expected value.",
        fields=(
            AssertionFieldTemplate(
                name="actual",
                label="Actual value",
                kind="expression",
                placeholder="{{response.json.duration_ms}}",
            ),
            AssertionFieldTemplate(
                name="expected",
                label="Threshold",
                kind="number",
                placeholder="1000",
            ),
        ),
    ),
)

_TEMPLATE_INDEX: dict[str, AssertionTemplate] = {template.operator: template for template in COMMON_ASSERTION_TEMPLATES}


def list_common_templates() -> list[dict[str, Any]]:
    """Return assertion templates in a JSON-serialisable structure."""

    return [template.to_dict() for template in COMMON_ASSERTION_TEMPLATES]


def get_template(operator: str) -> AssertionTemplate | None:
    return _TEMPLATE_INDEX.get(operator)


def validate_assertion_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalise an assertion definition."""

    try:
        definition = AssertionDefinition.model_validate(payload)
    except ValidationError as exc:
        raise ValueError("Invalid assertion definition") from exc
    return definition.model_dump(mode="json", exclude_none=True)


def normalise_assertions(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate and normalise a collection of assertion payloads."""

    normalised: list[dict[str, Any]] = []
    for item in items:
        normalised.append(validate_assertion_payload(dict(item or {})))
    return normalised


__all__ = [
    "AssertionFieldTemplate",
    "AssertionTemplate",
    "COMMON_ASSERTION_TEMPLATES",
    "get_template",
    "list_common_templates",
    "normalise_assertions",
    "validate_assertion_payload",
]
