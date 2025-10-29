from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.models.import_source import ImporterKind

PATH_PARAM_PATTERN = re.compile(r"\{([^{}]+)\}")
PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([^{}\s]+)\s*\}\}")
COLON_PARAM_PATTERN = re.compile(r"^:([A-Za-z0-9_.-]+)$")

SIGNIFICANT_FIELDS: tuple[str, ...] = (
    "name",
    "group_name",
    "path",
    "headers",
    "params",
    "body",
    "mock_example",
    "metadata",
)


@dataclass(slots=True)
class ImportCandidate:
    method: str
    path: str
    normalized_path: str
    version: str
    name: str
    group_name: str | None
    headers: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    body: dict[str, Any] = field(default_factory=dict)
    mock_example: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    source_key: str | None = None
    fingerprint: str | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "method": self.method,
            "path": self.path,
            "normalized_path": self.normalized_path,
            "version": self.version,
            "group_name": self.group_name,
            "headers": self.headers,
            "params": self.params,
            "body": self.body,
            "mock_example": self.mock_example,
            "metadata": self.metadata,
            "source_key": self.source_key,
        }


def normalize_method(method: str) -> str:
    return method.upper()


def normalize_path(path: str) -> str:
    if not path:
        return "/"

    working = path.strip()
    if not working.startswith("/"):
        working = f"/{working}"

    # Drop query string components if present.
    if "?" in working:
        working = working.split("?", 1)[0]

    # Collapse multiple slashes.
    while "//" in working:
        working = working.replace("//", "/")

    segments = [segment for segment in working.split("/") if segment]
    normalized_segments: list[str] = []
    for segment in segments:
        candidate = segment.strip()
        if not candidate:
            continue
        if candidate == "":
            continue
        if candidate.startswith("{") and candidate.endswith("}"):
            key = candidate[1:-1].strip()
            normalized_segments.append(_normalize_param_name(key))
            continue
        placeholder_match = PLACEHOLDER_PATTERN.fullmatch(candidate)
        if placeholder_match:
            normalized_segments.append(_normalize_param_name(placeholder_match.group(1)))
            continue
        colon_match = COLON_PARAM_PATTERN.fullmatch(candidate)
        if colon_match:
            normalized_segments.append(_normalize_param_name(colon_match.group(1)))
            continue
        normalized_segments.append(candidate)

    normalized = "/" + "/".join(normalized_segments)
    if len(normalized) > 1 and normalized.endswith("/"):
        normalized = normalized[:-1]
    if normalized == "":
        normalized = "/"
    return normalized


def _normalize_param_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "", name or "param")
    cleaned = cleaned or "param"
    return f"{{{cleaned}}}"


def compute_fingerprint(candidate: ImportCandidate) -> str:
    if candidate.fingerprint:
        return candidate.fingerprint
    payload = {
        "name": candidate.name,
        "group_name": candidate.group_name,
        "path": candidate.path,
        "headers": candidate.headers,
        "params": candidate.params,
        "body": candidate.body,
        "mock_example": candidate.mock_example,
        "metadata": candidate.metadata,
    }
    candidate.fingerprint = compute_hash(payload)
    return candidate.fingerprint


def compute_hash(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def diff_payload(existing: Any, candidate_value: Any) -> bool:
    return existing != candidate_value


def significant_fields() -> Iterable[str]:
    return SIGNIFICANT_FIELDS


__all__ = [
    "ImportCandidate",
    "ImporterKind",
    "compute_fingerprint",
    "compute_hash",
    "diff_payload",
    "normalize_method",
    "normalize_path",
    "significant_fields",
]
