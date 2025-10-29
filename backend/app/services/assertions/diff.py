from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, List, Literal

DiffChange = Literal["added", "removed", "changed", "type"]


@dataclass(slots=True)
class JsonDiff:
    path: str
    change: DiffChange
    expected: Any | None
    actual: Any | None

    def to_dict(self) -> dict[str, Any | None]:
        return {
            "path": self.path,
            "change": self.change,
            "expected": self.expected,
            "actual": self.actual,
        }


def diff_json(
    expected: Any,
    actual: Any,
    *,
    max_depth: int = 32,
    max_entries: int = 250,
) -> list[JsonDiff]:
    """Compute a semantic diff between two JSON-compatible payloads."""

    entries: list[JsonDiff] = []
    _diff_recursive(expected, actual, path="$", depth=0, entries=entries, max_depth=max_depth, max_entries=max_entries)
    return entries


def format_diff(entries: list[JsonDiff], *, max_characters: int = 8000) -> str | None:
    if not entries:
        return None
    lines: list[str] = []
    for entry in entries:
        lines.append(f"@@ {entry.path}")
        if entry.change == "added":
            lines.append(f"+ { _format_value(entry.actual) }")
        elif entry.change == "removed":
            lines.append(f"- { _format_value(entry.expected) }")
        elif entry.change == "type":
            lines.append(f"- type: { _describe_type(entry.expected) }")
            lines.append(f"+ type: { _describe_type(entry.actual) }")
        else:
            lines.append(f"- expected: { _format_value(entry.expected) }")
            lines.append(f"+ actual: { _format_value(entry.actual) }")
    text = "\n".join(lines)
    if len(text) > max_characters:
        return text[:max_characters] + "\n… diff truncated"
    return text


def _diff_recursive(
    expected: Any,
    actual: Any,
    *,
    path: str,
    depth: int,
    entries: List[JsonDiff],
    max_depth: int,
    max_entries: int,
) -> None:
    if len(entries) >= max_entries:
        return
    if depth >= max_depth:
        if _coerce_json(expected) != _coerce_json(actual):
            entries.append(JsonDiff(path=path, change="changed", expected=expected, actual=actual))
        return

    if type(expected) != type(actual):
        entries.append(JsonDiff(path=path, change="type", expected=expected, actual=actual))
        return

    if isinstance(expected, dict) and isinstance(actual, dict):
        expected_keys = set(expected.keys())
        actual_keys = set(actual.keys())
        for key in sorted(expected_keys - actual_keys):
            entries.append(JsonDiff(path=_extend_path(path, key), change="removed", expected=expected[key], actual=None))
            if len(entries) >= max_entries:
                return
        for key in sorted(actual_keys - expected_keys):
            entries.append(JsonDiff(path=_extend_path(path, key), change="added", expected=None, actual=actual[key]))
            if len(entries) >= max_entries:
                return
        for key in sorted(expected_keys & actual_keys):
            next_path = _extend_path(path, key)
            _diff_recursive(
                expected[key],
                actual[key],
                path=next_path,
                depth=depth + 1,
                entries=entries,
                max_depth=max_depth,
                max_entries=max_entries,
            )
            if len(entries) >= max_entries:
                return
        return

    if isinstance(expected, list) and isinstance(actual, list):
        common_length = min(len(expected), len(actual))
        for index in range(common_length):
            next_path = f"{path}[{index}]"
            _diff_recursive(
                expected[index],
                actual[index],
                path=next_path,
                depth=depth + 1,
                entries=entries,
                max_depth=max_depth,
                max_entries=max_entries,
            )
            if len(entries) >= max_entries:
                return
        if len(expected) > common_length:
            for index in range(common_length, len(expected)):
                next_path = f"{path}[{index}]"
                entries.append(JsonDiff(path=next_path, change="removed", expected=expected[index], actual=None))
                if len(entries) >= max_entries:
                    return
        if len(actual) > common_length:
            for index in range(common_length, len(actual)):
                next_path = f"{path}[{index}]"
                entries.append(JsonDiff(path=next_path, change="added", expected=None, actual=actual[index]))
                if len(entries) >= max_entries:
                    return
        return

    if _coerce_json(expected) != _coerce_json(actual):
        entries.append(JsonDiff(path=path, change="changed", expected=expected, actual=actual))


def _extend_path(base: str, key: Any) -> str:
    if isinstance(key, int):
        return f"{base}[{key}]"
    if isinstance(key, str) and key:
        if key.isidentifier():
            delimiter = "." if base != "$" else "."
            return f"{base}{delimiter}{key}"
        escaped = key.replace("'", "\\'")
        return f"{base}['{escaped}']"
    return f"{base}[{json.dumps(key)}]"


def _format_value(value: Any | None, *, limit: int = 160) -> str:
    formatted = _stringify(value)
    if len(formatted) <= limit:
        return formatted
    return formatted[: limit - 1] + "…"


def _stringify(value: Any | None) -> str:
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        if "\n" in value or len(value) > 160:
            return json.dumps(value, ensure_ascii=False)
        return value
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(value)


def _describe_type(value: Any | None) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _coerce_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        try:
            return json.loads(json.dumps(value, ensure_ascii=False))
        except (TypeError, ValueError):
            return value
    return value


__all__ = ["JsonDiff", "diff_json", "format_diff"]
