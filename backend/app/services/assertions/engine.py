from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from jsonpath_ng.exceptions import JsonPathParserError
from jsonpath_ng.ext import parse as jsonpath_parse
from pydantic import BaseModel

from app.services.assertions.diff import JsonDiff, diff_json, format_diff
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
    diff_entries: list[JsonDiff] | None = None
    diff_text: str | None = None

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

        diff_entries = self.diff_entries
        diff_text = self.diff_text

        if not self.passed:
            if diff_entries is None and isinstance(self.expected, (dict, list)) and isinstance(self.actual, (dict, list)):
                try:
                    diff_entries = diff_json(self.expected, self.actual)
                except Exception:  # pragma: no cover - guardrail
                    diff_entries = None
            if diff_entries:
                payload["diff_entries"] = [entry.to_dict() for entry in diff_entries]
                diff_text = diff_text or format_diff(diff_entries)
            if diff_text:
                payload["diff"] = diff_text
        else:
            if diff_entries:
                payload["diff_entries"] = [entry.to_dict() for entry in diff_entries]
            if diff_text:
                payload["diff"] = diff_text

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

        if definition.get("enabled") is False:
            return AssertionResult(
                name=name or f"assertion_{index}",
                operator=operator,
                passed=True,
                actual=None,
                expected=None,
                message="Assertion disabled",
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

    def _op_regex(self, definition: dict[str, Any], context: ExecutionContext, index: int) -> AssertionResult:
        return self._regex_assert(definition, context, index, operator_name="regex")

    def _op_regex_match(self, definition: dict[str, Any], context: ExecutionContext, index: int) -> AssertionResult:
        return self._regex_assert(definition, context, index, operator_name="regex_match")

    def _regex_assert(
        self,
        definition: dict[str, Any],
        context: ExecutionContext,
        index: int,
        *,
        operator_name: str,
    ) -> AssertionResult:
        actual = render_value(definition.get("actual"), context)
        pattern = render_value(definition.get("expected"), context)
        passed = False
        message: str | None = None
        if isinstance(actual, str) and isinstance(pattern, str):
            try:
                if re.search(pattern, actual):
                    passed = True
                else:
                    message = "Pattern did not match"
            except re.error as exc:
                message = f"Invalid regex pattern: {exc}"
        else:
            message = "Regex assertions require string actual and pattern values"
        return AssertionResult(
            name=_name(definition, index),
            operator=operator_name,
            passed=passed,
            actual=actual,
            expected=pattern,
            message=message if not passed else None,
        )

    def _op_length(self, definition: dict[str, Any], context: ExecutionContext, index: int) -> AssertionResult:
        collection = render_value(definition.get("actual"), context)
        expected_raw = render_value(definition.get("expected"), context)
        try:
            expected_length = _coerce_int(expected_raw)
        except ValueError:
            return AssertionResult(
                name=_name(definition, index),
                operator="length",
                passed=False,
                actual=None,
                expected=expected_raw,
                message="Length assertions require an integer expected value",
            )
        try:
            actual_length = len(collection)  # type: ignore[arg-type]
        except TypeError:
            return AssertionResult(
                name=_name(definition, index),
                operator="length",
                passed=False,
                actual=None,
                expected=expected_length,
                message="Length assertions require a value with a measurable length",
            )
        passed = actual_length == expected_length
        message = None if passed else f"Expected length {expected_length}, got {actual_length}"
        return AssertionResult(
            name=_name(definition, index),
            operator="length",
            passed=passed,
            actual=actual_length,
            expected=expected_length,
            message=message,
        )

    def _op_gt(self, definition: dict[str, Any], context: ExecutionContext, index: int) -> AssertionResult:
        actual_raw = render_value(definition.get("actual"), context)
        expected_raw = render_value(definition.get("expected"), context)
        try:
            actual_value = _coerce_number(actual_raw)
            expected_value = _coerce_number(expected_raw)
        except ValueError:
            return AssertionResult(
                name=_name(definition, index),
                operator="gt",
                passed=False,
                actual=actual_raw,
                expected=expected_raw,
                message="Greater than assertions require numeric values",
            )
        passed = float(actual_value) > float(expected_value)
        message = None if passed else f"Expected {actual_value} to be greater than {expected_value}"
        return AssertionResult(
            name=_name(definition, index),
            operator="gt",
            passed=passed,
            actual=actual_value,
            expected=expected_value,
            message=message,
        )

    def _op_lt(self, definition: dict[str, Any], context: ExecutionContext, index: int) -> AssertionResult:
        actual_raw = render_value(definition.get("actual"), context)
        expected_raw = render_value(definition.get("expected"), context)
        try:
            actual_value = _coerce_number(actual_raw)
            expected_value = _coerce_number(expected_raw)
        except ValueError:
            return AssertionResult(
                name=_name(definition, index),
                operator="lt",
                passed=False,
                actual=actual_raw,
                expected=expected_raw,
                message="Less than assertions require numeric values",
            )
        passed = float(actual_value) < float(expected_value)
        message = None if passed else f"Expected {actual_value} to be less than {expected_value}"
        return AssertionResult(
            name=_name(definition, index),
            operator="lt",
            passed=passed,
            actual=actual_value,
            expected=expected_value,
            message=message,
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

    def _convert(item: Any) -> dict[str, Any] | None:
        if isinstance(item, dict):
            return dict(item)
        if isinstance(item, BaseModel):
            return item.model_dump(mode="python", exclude_none=True)
        return None

    normalised: list[dict[str, Any]] = []
    if isinstance(assertions, list):
        for definition in assertions:
            payload = _convert(definition)
            if not payload:
                continue
            if payload.get("enabled") is False:
                continue
            operator = payload.get("operator")
            if isinstance(operator, str):
                payload["operator"] = operator.strip().lower()
            normalised.append(payload)
        return normalised

    if isinstance(assertions, dict):
        items = assertions.get("items")
        if isinstance(items, list):
            for definition in items:
                payload = _convert(definition)
                if not payload:
                    continue
                if payload.get("enabled") is False:
                    continue
                operator = payload.get("operator")
                if isinstance(operator, str):
                    payload["operator"] = operator.strip().lower()
                normalised.append(payload)
            return normalised
        for operator, value in assertions.items():
            if operator == "items":
                continue
            payload = {"operator": str(operator).strip().lower(), "expected": value}
            normalised.append(payload)
        return normalised

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


def _coerce_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("Boolean values are not valid integers")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise ValueError("Value is not an integer")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("Empty string is not a valid integer")
        try:
            if "." in text or "e" in text.lower():
                float_value = float(text)
                if float_value.is_integer():
                    return int(float_value)
                raise ValueError("Value is not an integer")
            return int(text)
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError("Value is not an integer") from exc
    raise ValueError("Unsupported type for integer conversion")


def _coerce_number(value: Any) -> int | float:
    if isinstance(value, bool):
        raise ValueError("Boolean values are not valid numbers")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("Empty string is not a valid number")
        try:
            number = float(text)
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError("Value is not numeric") from exc
        return int(number) if number.is_integer() else number
    raise ValueError("Unsupported type for numeric conversion")
