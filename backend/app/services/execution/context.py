from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Iterable

from jsonpath_ng.exceptions import JsonPathParserError
from jsonpath_ng.ext import parse as jsonpath_parse

_TEMPLATE_PATTERN = re.compile(r"{{\s*(?P<expr>[^{}]+)\s*}}")
_SIMPLE_TEMPLATE_PATTERN = re.compile(r"^{{\s*(?P<expr>[^{}]+)\s*}}$")
_JSONPATH_CALL_PATTERN = re.compile(r"jsonpath\((?P<quote>['\"])(?P<expr>.+?)(?P=quote)\)")


@dataclass
class ExecutionContext:
    """Holds execution-scoped variables and prior step results for templating."""

    variables: dict[str, Any] = field(default_factory=dict)
    previous_steps: dict[str, dict[str, Any]] = field(default_factory=dict)
    current_response: dict[str, Any] | None = None
    environment: dict[str, Any] = field(default_factory=dict)
    dataset_row: dict[str, Any] | None = None
    secrets: dict[str, Any] = field(default_factory=dict)

    def clone(self) -> ExecutionContext:
        return ExecutionContext(
            variables=deepcopy(self.variables),
            previous_steps=deepcopy(self.previous_steps),
            current_response=deepcopy(self.current_response),
            environment=deepcopy(self.environment),
            dataset_row=deepcopy(self.dataset_row),
            secrets=deepcopy(self.secrets),
        )

    def remember_step(self, alias: str, response: dict[str, Any]) -> None:
        self.previous_steps[alias] = response

    def set_current_response(self, response: dict[str, Any] | None) -> None:
        self.current_response = response


def render_value(value: Any, context: ExecutionContext) -> Any:
    if isinstance(value, str):
        return _render_string(value, context)
    if isinstance(value, dict):
        return {key: render_value(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [render_value(item, context) for item in value]
    return value


def _render_string(template: str, context: ExecutionContext) -> Any:
    if "{{" not in template or "}}" not in template:
        return template

    simple = _SIMPLE_TEMPLATE_PATTERN.fullmatch(template)
    if simple:
        expr = simple.group("expr")
        return _resolve_expression(expr, context)

    def _replace(match: re.Match[str]) -> str:
        expr = match.group("expr")
        resolved = _resolve_expression(expr, context)
        return "" if resolved is None else str(resolved)

    return _TEMPLATE_PATTERN.sub(_replace, template)


def _resolve_expression(expr: str, context: ExecutionContext) -> Any:
    expr = expr.strip()
    if not expr:
        return None

    segments = expr.split(".")
    root = segments[0]
    remainder = segments[1:]

    if root == "variables":
        return _traverse(context.variables, remainder)
    if root == "env":
        return _traverse(context.environment, remainder)
    if root == "row":
        return _traverse(context.dataset_row, remainder)
    if root == "secret":
        return _traverse(context.secrets, remainder)
    if root == "prev":
        if not remainder:
            return None
        alias = remainder[0]
        step_data = context.previous_steps.get(alias)
        return _traverse_response(step_data, remainder[1:])
    if root == "response":
        return _traverse_response(context.current_response, remainder)

    # Fallback to variables using the full path
    return _traverse(context.variables, segments)


def _traverse(data: Any, path: Iterable[str]) -> Any:
    current = data
    for segment in path:
        if current is None:
            return None
        jsonpath_match = _JSONPATH_CALL_PATTERN.fullmatch(segment)
        if jsonpath_match:
            target = current
            if isinstance(current, dict) and "json" in current:
                target = current.get("json")
            return _apply_jsonpath(target, jsonpath_match.group("expr"))
        if isinstance(current, dict):
            current = current.get(segment)
            continue
        if isinstance(current, list):
            try:
                index = int(segment)
            except (TypeError, ValueError):
                return None
            if -len(current) <= index < len(current):
                current = current[index]
            else:
                return None
            continue
        return None
    return current


def _traverse_response(data: Any, path: Iterable[str]) -> Any:
    if data is None:
        return None
    current = data
    for segment in path:
        if current is None:
            return None
        jsonpath_match = _JSONPATH_CALL_PATTERN.fullmatch(segment)
        if jsonpath_match:
            payload = current
            if isinstance(current, dict) and "json" in current:
                payload = current.get("json")
            return _apply_jsonpath(payload, jsonpath_match.group("expr"))
        if isinstance(current, dict):
            current = current.get(segment)
            continue
        if isinstance(current, list):
            try:
                index = int(segment)
            except (TypeError, ValueError):
                return None
            if -len(current) <= index < len(current):
                current = current[index]
            else:
                return None
            continue
        return None
    return current


def _apply_jsonpath(data: Any, expression: str) -> Any:
    if data is None:
        return None
    try:
        parsed = jsonpath_parse(expression)
    except JsonPathParserError as exc:
        raise ValueError(f"Invalid jsonpath expression: {expression}") from exc

    matches = [match.value for match in parsed.find(data)]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    return matches

