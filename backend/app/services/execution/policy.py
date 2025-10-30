from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Iterable

from app.core.config import Settings, get_settings
from app.models.execution_policy import ExecutionPolicy

_DEFAULT_BACKOFF: dict[str, Any] = {
    "strategy": "exponential_jitter",
    "base_seconds": 1.5,
    "max_seconds": 30.0,
    "jitter_ratio": 0.5,
    "retry_on_assertions": False,
    "cooldown_seconds": 30.0,
}
_DEFAULT_RETRY_MAX_ATTEMPTS = 3
_DEFAULT_CIRCUIT_THRESHOLD = 5
_DEFAULT_CIRCUIT_WINDOW = 60
_DEFAULT_PRIORITY = 5
_DEFAULT_POLICY_NAME = "default"


def _coerce_float(value: Any, fallback: float) -> float:
    try:
        if value is None:
            return float(fallback)
        if isinstance(value, str) and not value.strip():
            return float(fallback)
        return float(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return float(fallback)


def _coerce_int(value: Any, fallback: int) -> int:
    try:
        if value is None:
            return int(fallback)
        if isinstance(value, str) and not value.strip():
            return int(fallback)
        return int(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return int(fallback)


def _normalize_tags(values: Iterable[Any] | None) -> tuple[str, ...]:
    if not values:
        return tuple()
    sanitized: list[str] = []
    seen: set[str] = set()
    for item in values:
        if item is None:
            continue
        candidate = str(item).strip()
        if not candidate:
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        sanitized.append(candidate)
    return tuple(sanitized)


@dataclass(frozen=True)
class QueueSnapshot:
    id: str | None
    name: str | None
    routing_key: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "routing_key": self.routing_key,
        }


@dataclass(frozen=True)
class RetryBackoffSnapshot:
    strategy: str
    base_seconds: float
    max_seconds: float
    jitter_ratio: float
    retry_on_assertions: bool
    cooldown_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "base_seconds": self.base_seconds,
            "max_seconds": self.max_seconds,
            "jitter_ratio": self.jitter_ratio,
            "retry_on_assertions": self.retry_on_assertions,
            "cooldown_seconds": self.cooldown_seconds,
        }


@dataclass(frozen=True)
class ExecutionPolicySnapshot:
    id: str | None
    name: str
    max_concurrency: int | None
    per_host_qps: float | None
    queue: QueueSnapshot | None
    priority: int
    retry_max_attempts: int
    retry_backoff: RetryBackoffSnapshot
    timeout_seconds: float
    circuit_breaker_threshold: int
    circuit_breaker_window_seconds: int
    tags_include: tuple[str, ...]
    tags_exclude: tuple[str, ...]
    enabled: bool = True

    @property
    def key(self) -> str:
        return self.id or f"{_DEFAULT_POLICY_NAME}:{self.name.lower()}"

    def to_dict(self) -> dict[str, Any]:
        queue_payload = self.queue.to_dict() if self.queue else None
        return {
            "id": self.id,
            "name": self.name,
            "max_concurrency": self.max_concurrency,
            "per_host_qps": self.per_host_qps,
            "queue": queue_payload,
            "queue_id": queue_payload["id"] if queue_payload else None,
            "priority": self.priority,
            "retry_max_attempts": self.retry_max_attempts,
            "retry_backoff": self.retry_backoff.to_dict(),
            "timeout_seconds": self.timeout_seconds,
            "circuit_breaker_threshold": self.circuit_breaker_threshold,
            "circuit_breaker_window_seconds": self.circuit_breaker_window_seconds,
            "tags": {
                "include": list(self.tags_include),
                "exclude": list(self.tags_exclude),
            },
            "tags_include": list(self.tags_include),
            "tags_exclude": list(self.tags_exclude),
            "enabled": self.enabled,
        }


def _resolve_backoff(raw: dict[str, Any] | None, settings: Settings) -> RetryBackoffSnapshot:
    if raw is None:
        raw = {}
    payload = {**_DEFAULT_BACKOFF, **raw}
    strategy = str(payload.get("strategy") or _DEFAULT_BACKOFF["strategy"])
    base_seconds = max(0.1, _coerce_float(payload.get("base_seconds"), _DEFAULT_BACKOFF["base_seconds"]))
    max_seconds = max(base_seconds, _coerce_float(payload.get("max_seconds"), _DEFAULT_BACKOFF["max_seconds"]))
    jitter_ratio = payload.get("jitter_ratio", _DEFAULT_BACKOFF["jitter_ratio"])
    jitter_ratio = max(0.0, min(_coerce_float(jitter_ratio, _DEFAULT_BACKOFF["jitter_ratio"]), 1.0))
    retry_on_assertions = bool(payload.get("retry_on_assertions", _DEFAULT_BACKOFF["retry_on_assertions"]))
    cooldown_seconds = max(1.0, _coerce_float(payload.get("cooldown_seconds"), _DEFAULT_BACKOFF["cooldown_seconds"]))
    return RetryBackoffSnapshot(
        strategy=strategy,
        base_seconds=base_seconds,
        max_seconds=max_seconds,
        jitter_ratio=jitter_ratio,
        retry_on_assertions=retry_on_assertions,
        cooldown_seconds=cooldown_seconds,
    )


def _queue_snapshot(policy: ExecutionPolicy | None) -> QueueSnapshot | None:
    if policy is None or policy.queue_id is None:
        return None
    queue_obj = getattr(policy, "queue", None)
    if queue_obj is None:
        return QueueSnapshot(id=str(policy.queue_id), name=None, routing_key=None)
    return QueueSnapshot(
        id=str(queue_obj.id) if queue_obj.id else str(policy.queue_id),
        name=getattr(queue_obj, "name", None),
        routing_key=getattr(queue_obj, "routing_key", None),
    )


def _coerce_policy_id(policy: ExecutionPolicy | dict[str, Any] | None) -> str | None:
    if policy is None:
        return None
    if isinstance(policy, ExecutionPolicy):
        return str(policy.id)
    raw_id = policy.get("id") if isinstance(policy, dict) else None
    try:
        return str(uuid.UUID(str(raw_id))) if raw_id is not None else None
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None


def execution_policy_to_snapshot(
    policy: ExecutionPolicy | None,
    *,
    settings: Settings | None = None,
) -> ExecutionPolicySnapshot:
    active_settings = settings or get_settings()
    if policy is None:
        return default_policy_snapshot(settings=active_settings)

    backoff_snapshot = _resolve_backoff(policy.retry_backoff, active_settings)
    per_host_qps = policy.per_host_qps
    if per_host_qps is not None and per_host_qps <= 0:
        per_host_qps = None
    max_concurrency = policy.max_concurrency
    if max_concurrency is not None and max_concurrency <= 0:
        max_concurrency = None

    retry_max_attempts = max(1, min(int(policy.retry_max_attempts or _DEFAULT_RETRY_MAX_ATTEMPTS), 10))
    timeout_seconds = max(0.1, _coerce_float(policy.timeout_seconds, active_settings.request_timeout_seconds))
    circuit_breaker_threshold = max(0, _coerce_int(policy.circuit_breaker_threshold, _DEFAULT_CIRCUIT_THRESHOLD))
    circuit_breaker_window_seconds = max(1, _coerce_int(
        getattr(policy, "circuit_breaker_window_seconds", _DEFAULT_CIRCUIT_WINDOW),
        _DEFAULT_CIRCUIT_WINDOW,
    ))
    priority = max(0, min(_coerce_int(getattr(policy, "priority", _DEFAULT_PRIORITY), _DEFAULT_PRIORITY), 9))
    tags_include = _normalize_tags(getattr(policy, "tags_include", None))
    tags_exclude = _normalize_tags(getattr(policy, "tags_exclude", None))
    queue = _queue_snapshot(policy)

    return ExecutionPolicySnapshot(
        id=str(policy.id),
        name=policy.name,
        max_concurrency=max_concurrency,
        per_host_qps=per_host_qps,
        queue=queue,
        priority=priority,
        retry_max_attempts=retry_max_attempts,
        retry_backoff=backoff_snapshot,
        timeout_seconds=timeout_seconds,
        circuit_breaker_threshold=circuit_breaker_threshold,
        circuit_breaker_window_seconds=circuit_breaker_window_seconds,
        tags_include=tags_include,
        tags_exclude=tags_exclude,
        enabled=policy.enabled,
    )


def snapshot_from_dict(
    payload: dict[str, Any] | None,
    *,
    settings: Settings | None = None,
) -> ExecutionPolicySnapshot:
    if payload is None:
        return default_policy_snapshot(settings=settings)
    active_settings = settings or get_settings()
    backoff_snapshot = _resolve_backoff(payload.get("retry_backoff"), active_settings)
    policy_id = _coerce_policy_id(payload)
    name = str(payload.get("name") or _DEFAULT_POLICY_NAME)
    max_concurrency = payload.get("max_concurrency")
    if max_concurrency is not None:
        max_concurrency = max(0, int(max_concurrency))
        if max_concurrency == 0:
            max_concurrency = None
    per_host_qps = payload.get("per_host_qps")
    if per_host_qps is not None:
        per_host_qps = _coerce_float(per_host_qps, 0.0)
        if per_host_qps <= 0:
            per_host_qps = None
    queue_payload = payload.get("queue")
    if isinstance(queue_payload, dict):
        queue_snapshot = QueueSnapshot(
            id=str(queue_payload.get("id")) if queue_payload.get("id") else None,
            name=queue_payload.get("name"),
            routing_key=queue_payload.get("routing_key"),
        )
    else:
        queue_id = payload.get("queue_id")
        queue_snapshot = QueueSnapshot(id=str(queue_id), name=None, routing_key=None) if queue_id else None
    retry_max_attempts = payload.get("retry_max_attempts", _DEFAULT_RETRY_MAX_ATTEMPTS)
    retry_max_attempts = max(1, min(int(retry_max_attempts), 10))
    timeout_seconds = payload.get("timeout_seconds", active_settings.request_timeout_seconds)
    timeout_seconds = max(0.1, _coerce_float(timeout_seconds, active_settings.request_timeout_seconds))
    circuit_breaker_threshold = payload.get("circuit_breaker_threshold", _DEFAULT_CIRCUIT_THRESHOLD)
    circuit_breaker_threshold = max(0, _coerce_int(circuit_breaker_threshold, _DEFAULT_CIRCUIT_THRESHOLD))
    circuit_breaker_window_seconds = payload.get("circuit_breaker_window_seconds", _DEFAULT_CIRCUIT_WINDOW)
    circuit_breaker_window_seconds = max(1, _coerce_int(circuit_breaker_window_seconds, _DEFAULT_CIRCUIT_WINDOW))
    priority = payload.get("priority", _DEFAULT_PRIORITY)
    priority = max(0, min(_coerce_int(priority, _DEFAULT_PRIORITY), 9))
    tags_section = payload.get("tags") if isinstance(payload.get("tags"), dict) else {}
    tags_include = _normalize_tags(payload.get("tags_include")) or _normalize_tags(tags_section.get("include"))
    tags_exclude = _normalize_tags(payload.get("tags_exclude")) or _normalize_tags(tags_section.get("exclude"))
    enabled = bool(payload.get("enabled", True))

    return ExecutionPolicySnapshot(
        id=policy_id,
        name=name,
        max_concurrency=max_concurrency,
        per_host_qps=per_host_qps,
        queue=queue_snapshot,
        priority=priority,
        retry_max_attempts=retry_max_attempts,
        retry_backoff=backoff_snapshot,
        timeout_seconds=timeout_seconds,
        circuit_breaker_threshold=circuit_breaker_threshold,
        circuit_breaker_window_seconds=circuit_breaker_window_seconds,
        tags_include=tags_include,
        tags_exclude=tags_exclude,
        enabled=enabled,
    )


def default_policy_snapshot(*, settings: Settings | None = None) -> ExecutionPolicySnapshot:
    active_settings = settings or get_settings()
    backoff_snapshot = _resolve_backoff(
        {
            "strategy": "exponential_jitter",
            "base_seconds": active_settings.httpx_retry_backoff_factor,
            "max_seconds": max(
                active_settings.httpx_retry_backoff_factor * 8,
                _DEFAULT_BACKOFF["max_seconds"],
            ),
            "jitter_ratio": _DEFAULT_BACKOFF["jitter_ratio"],
            "retry_on_assertions": False,
            "cooldown_seconds": _DEFAULT_BACKOFF["cooldown_seconds"],
        },
        active_settings,
    )
    retry_max_attempts = max(1, min(int(active_settings.httpx_retry_attempts), 10))
    timeout_seconds = max(0.1, float(active_settings.request_timeout_seconds))

    return ExecutionPolicySnapshot(
        id=None,
        name=_DEFAULT_POLICY_NAME,
        max_concurrency=None,
        per_host_qps=None,
        queue=None,
        priority=_DEFAULT_PRIORITY,
        retry_max_attempts=retry_max_attempts,
        retry_backoff=backoff_snapshot,
        timeout_seconds=timeout_seconds,
        circuit_breaker_threshold=_DEFAULT_CIRCUIT_THRESHOLD,
        circuit_breaker_window_seconds=_DEFAULT_CIRCUIT_WINDOW,
        tags_include=tuple(),
        tags_exclude=tuple(),
        enabled=True,
    )


__all__ = [
    "ExecutionPolicySnapshot",
    "QueueSnapshot",
    "RetryBackoffSnapshot",
    "execution_policy_to_snapshot",
    "snapshot_from_dict",
    "default_policy_snapshot",
]
