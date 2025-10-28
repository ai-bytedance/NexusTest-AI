from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from jsonpath_ng.exceptions import JsonPathParserError
from jsonpath_ng.ext import parse as jsonpath_parse

from app.services.execution.context import ExecutionContext, render_value


@dataclass
class AssertionResult:
    name: str | None
    operator: str
    passed: bool
    actual: Any
    expected: Any
    message: str | None = None
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "operator": self.operator,
            "passed": self.passed,
            "actual": self.actual,
            "expected": self.expected,
        }
        if self.message is not None:
            payload["message"] = self.message
        if self.path is not None:
            payload["path"] = self.path
        return payload


class AssertionEngine:
    def evaluate(
        self,
        assertions: Iterable[dict[str, Any]] | dict[str, Any] | None,
        response_context: dict[str, Any],
        context: ExecutionContext,
    ) -> tuple[bool, list[AssertionResult]]:
        definitions = _normalise_assertions(assertions)
        if not definitions:
            return True, []

        context.set_current_response(response_context)

        results: list[AssertionResult] = []
        for index, definition in enumerate(definitions):
            result = self._evaluate_definition(definition, context, index)
            results.append(result)
        passed = all(item.passed for item in results)
        return passed, results

    def _evaluate_definition(
        self,
        definition: dict[str, Any],
        context: ExecutionContext,
        index: int,
    ) -> AssertionResult:
        operator = str(definition.get("operator", "")).strip().lower()
        name = definition.get("name")
        if not operator:
            return AssertionResult(
                name=name or f"assertion_{index}",
                operator="unknown",
                passed=False,
                actual=None,
                expected=None,
                message="Assertion operator is required",
            )

        handler = getattr(self, f"_op_{operator}", None)
        if handler is None:
            return AssertionResult(
                name=name or f"assertion_{index}",
                operator=operator,
                passed=False,
                actual=None,
                expected=None,
                message=f"Unsupported assertion operator '{operator}'",
            )

        try:
            return handler(definition, context, index)
        except Exception as exc:  # pragma: no cover - guardrail
            return AssertionResult(
                name=name or f"assertion_{index}",
                operator=operator,
                passed=False,
                actual=None,
                expected=None,
                message=str(exc),
            )

    def _op_status_code(self, definition: dict[str, Any], context: ExecutionContext, index: int) -> AssertionResult:
        expected = render_value(definition.get("expected"), context)
        actual = context.current_response.get("status_code") if context.current_response else None
        passed = actual == expected
        return AssertionResult(
            name=_name(definition, index),
            operator="status_code",
            passed=passed,
            actual=actual,
            expected=expected,
            message=None if passed else "Status code did not match",
        )

    def _op_equals(self, definition: dict[str, Any], context: ExecutionContext, index: int) -> AssertionResult:
        actual = render_value(definition.get("actual"), context)
        expected = render_value(definition.get("expected"), context)
        passed = actual == expected
        return AssertionResult(
            name=_name(definition, index),
            operator="equals",
            passed=passed,
            actual=actual,
            expected=expected,
            message=None if passed else "Values are not equal",
        )

    def _op_not_equals(self, definition: dict[str, Any], context: ExecutionContext, index: int) -> AssertionResult:
        actual = render_value(definition.get("actual"), context)
        expected = render_value(definition.get("expected"), context)
        passed = actual != expected
        return AssertionResult(
            name=_name(definition, index),
            operator="not_equals",
            passed=passed,
            actual=actual,
            expected=expected,
            message=None if passed else "Values are equal",
        )

    def _op_contains(self, definition: dict[str, Any], context: ExecutionContext, index: int) -> AssertionResult:
        actual = render_value(definition.get("actual"), context)
        expected = render_value(definition.get("expected"), context)
        passed = _contains(actual, expected)
        return AssertionResult(
            name=_name(definition, index),
            operator="contains",
            passed=passed,
            actual=actual,
            expected=expected,
            message=None if passed else "Expected value not found",
        )

    def _op_not_contains(self, definition: dict[str, Any], context: ExecutionContext, index: int) -> AssertionResult:
        actual = render_value(definition.get("actual"), context)
        expected = render_value(definition.get("expected"), context)
        passed = not _contains(actual, expected)
        return AssertionResult(
            name=_name(definition, index),
            operator="not_contains",
            passed=passed,
            actual=actual,
            expected=expected,
            message=None if passed else "Unexpected value present",
        )

    def _op_regex_match(self, definition: dict[str, Any], context: ExecutionContext, index: int) -> AssertionResult:
        actual = render_value(definition.get("actual"), context)
        pattern = render_value(definition.get("expected"), context)
        passed = False
        message = ""
        if isinstance(actual, str) and isinstance(pattern, str):
            if re.search(pattern, actual):
                passed = True
            else:
                message = "Pattern did not match"
        else:
            message = "Regex requires string actual and expected values"
        return AssertionResult(
            name=_name(definition, index),
            operator="regex_match",
            passed=passed,
            actual=actual,
            expected=pattern,
            message=None if passed else message,
        )

    def _op_jsonpath_equals(self, definition: dict[str, Any], context: ExecutionContext, index: int) -> AssertionResult:
        path = render_value(definition.get("path"), context)
        expected = render_value(definition.get("expected"), context)
        values = _extract_jsonpath(context.current_response, path)
        actual = _single_or_list(values)
        passed = actual == expected
        message = None if passed else "JSONPath equality assertion failed"
        return AssertionResult(
            name=_name(definition, index),
            operator="jsonpath_equals",
            passed=passed,
            actual=actual,
            expected=expected,
            message=message,
            path=path,
        )

    def _op_jsonpath_contains(self, definition: dict[str, Any], context: ExecutionContext, index: int) -> AssertionResult:
        path = render_value(definition.get("path"), context)
        expected = render_value(definition.get("expected"), context)
        values = _extract_jsonpath(context.current_response, path)
        actual = _single_or_list(values)
        passed = _contains(actual, expected)
        message = None if passed else "Expected value not present in JSONPath result"
        return AssertionResult(
            name=_name(definition, index),
            operator="jsonpath_contains",
            passed=passed,
            actual=actual,
            expected=expected,
            message=message,
            path=path,
        )

    def _op_status(self, definition: dict[str, Any], context: ExecutionContext, index: int) -> AssertionResult:  # pragma: no cover
        actual = render_value(definition.get("actual"), context)
        expected = render_value(definition.get("expected"), context)
        passed = actual == expected
        return AssertionResult(
            name=_name(definition, index),
            operator="status",
            passed=passed,
            actual=actual,
            expected=expected,
            message=None if passed else "Status assertion failed",
        )


def _normalise_assertions(assertions: Iterable[dict[str, Any]] | dict[str, Any] | None) -> list[dict[str, Any]]:
    if assertions is None:
        return []
    if isinstance(assertions, list):
        return [definition for definition in assertions if isinstance(definition, dict)]
    if isinstance(assertions, dict):
        items = assertions.get("items")
        if isinstance(items, list):
            return [definition for definition in items if isinstance(definition, dict)]
        return [
            {"operator": str(operator), "expected": value}
            for operator, value in assertions.items()
            if operator != "items"
        ]
    return []


def _name(definition: dict[str, Any], index: int) -> str:
    name = definition.get("name")
    if isinstance(name, str) and name.strip():
        return name
    return f"assertion_{index}"


def _contains(actual: Any, expected: Any) -> bool:
    if actual is None:
        return expected is None
    if isinstance(actual, str):
        return str(expected) in actual
    if isinstance(actual, (list, tuple, set)):
        return expected in actual
    return actual == expected


def _extract_jsonpath(response_context: dict[str, Any] | None, path: Any) -> list[Any]:
    if not isinstance(path, str) or not path.strip():
        raise ValueError("JSONPath expression is required")
    payload = {}
    if response_context and "json" in response_context and response_context["json"] is not None:
        payload = response_context["json"]
    try:
        expression = jsonpath_parse(path)
    except JsonPathParserError as exc:
        raise ValueError(f"Invalid jsonpath expression: {path}") from exc

    return [match.value for match in expression.find(payload)]


def _single_or_list(values: list[Any]) -> Any:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return values
