from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings, get_settings
from app.models.execution_policy import ExecutionPolicy

_DEFAULT_BACKOFF: dict[str, Any] = {
    "base_seconds": 1.5,
    "max_seconds": 30.0,
    "jitter_ratio": 0.5,
    "retry_on_assertions": False,
    "cooldown_seconds": 30.0,
}
_DEFAULT_RETRY_MAX_ATTEMPTS = 3
_DEFAULT_TIMEOUT_SECONDS = 30
_DEFAULT_CIRCUIT_THRESHOLD = 5
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


@dataclass(frozen=True)
class RetryBackoffSnapshot:
    base_seconds: float
    max_seconds: float
    jitter_ratio: float
    retry_on_assertions: bool
    cooldown_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
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
    retry_max_attempts: int
    retry_backoff: RetryBackoffSnapshot
    timeout_seconds: float
    circuit_breaker_threshold: int
    enabled: bool = True

    @property
    def key(self) -> str:
        return self.id or f"{_DEFAULT_POLICY_NAME}:{self.name.lower()}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "max_concurrency": self.max_concurrency,
            "per_host_qps": self.per_host_qps,
            "retry_max_attempts": self.retry_max_attempts,
            "retry_backoff": self.retry_backoff.to_dict(),
            "timeout_seconds": self.timeout_seconds,
            "circuit_breaker_threshold": self.circuit_breaker_threshold,
            "enabled": self.enabled,
        }


def _resolve_backoff(raw: dict[str, Any] | None, settings: Settings) -> RetryBackoffSnapshot:
    if raw is None:
        raw = {}
    payload = {**_DEFAULT_BACKOFF, **raw}
    base_seconds = max(0.1, _coerce_float(payload.get("base_seconds"), _DEFAULT_BACKOFF["base_seconds"]))
    max_seconds = max(base_seconds, _coerce_float(payload.get("max_seconds"), _DEFAULT_BACKOFF["max_seconds"]))
    jitter_ratio = payload.get("jitter_ratio", _DEFAULT_BACKOFF["jitter_ratio"])
    jitter_ratio = max(0.0, min(_coerce_float(jitter_ratio, _DEFAULT_BACKOFF["jitter_ratio"]), 1.0))
    retry_on_assertions = bool(payload.get("retry_on_assertions", _DEFAULT_BACKOFF["retry_on_assertions"]))
    cooldown_seconds = max(1.0, _coerce_float(payload.get("cooldown_seconds"), _DEFAULT_BACKOFF["cooldown_seconds"]))
    return RetryBackoffSnapshot(
        base_seconds=base_seconds,
        max_seconds=max_seconds,
        jitter_ratio=jitter_ratio,
        retry_on_assertions=retry_on_assertions,
        cooldown_seconds=cooldown_seconds,
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
    if per_host_qps is not None and per_host_qps < 0:
        per_host_qps = None
    max_concurrency = policy.max_concurrency
    if max_concurrency is not None and max_concurrency < 0:
        max_concurrency = None

    retry_max_attempts = max(1, min(int(policy.retry_max_attempts or _DEFAULT_RETRY_MAX_ATTEMPTS), 5))
    timeout_seconds = max(1.0, _coerce_float(policy.timeout_seconds, active_settings.request_timeout_seconds))
    circuit_breaker_threshold = max(1, _coerce_int(policy.circuit_breaker_threshold, _DEFAULT_CIRCUIT_THRESHOLD))

    return ExecutionPolicySnapshot(
        id=str(policy.id),
        name=policy.name,
        max_concurrency=max_concurrency,
        per_host_qps=per_host_qps,
        retry_max_attempts=retry_max_attempts,
        retry_backoff=backoff_snapshot,
        timeout_seconds=timeout_seconds,
        circuit_breaker_threshold=circuit_breaker_threshold,
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
    retry_max_attempts = payload.get("retry_max_attempts", _DEFAULT_RETRY_MAX_ATTEMPTS)
    retry_max_attempts = max(1, min(int(retry_max_attempts), 5))
    timeout_seconds = payload.get("timeout_seconds", active_settings.request_timeout_seconds)
    timeout_seconds = max(1.0, _coerce_float(timeout_seconds, active_settings.request_timeout_seconds))
    circuit_breaker_threshold = payload.get("circuit_breaker_threshold", _DEFAULT_CIRCUIT_THRESHOLD)
    circuit_breaker_threshold = max(1, _coerce_int(circuit_breaker_threshold, _DEFAULT_CIRCUIT_THRESHOLD))
    enabled = bool(payload.get("enabled", True))

    return ExecutionPolicySnapshot(
        id=policy_id,
        name=name,
        max_concurrency=max_concurrency,
        per_host_qps=per_host_qps,
        retry_max_attempts=retry_max_attempts,
        retry_backoff=backoff_snapshot,
        timeout_seconds=timeout_seconds,
        circuit_breaker_threshold=circuit_breaker_threshold,
        enabled=enabled,
    )


def default_policy_snapshot(*, settings: Settings | None = None) -> ExecutionPolicySnapshot:
    active_settings = settings or get_settings()
    backoff_snapshot = _resolve_backoff(
        {
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
    retry_max_attempts = max(1, min(int(active_settings.httpx_retry_attempts), 5))
    timeout_seconds = max(1.0, float(active_settings.request_timeout_seconds))

    return ExecutionPolicySnapshot(
        id=None,
        name=_DEFAULT_POLICY_NAME,
        max_concurrency=None,
        per_host_qps=None,
        retry_max_attempts=retry_max_attempts,
        retry_backoff=backoff_snapshot,
        timeout_seconds=timeout_seconds,
        circuit_breaker_threshold=_DEFAULT_CIRCUIT_THRESHOLD,
        enabled=True,
    )


__all__ = [
    "ExecutionPolicySnapshot",
    "RetryBackoffSnapshot",
    "execution_policy_to_snapshot",
    "snapshot_from_dict",
    "default_policy_snapshot",
]
