from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import IdentifierModel, ORMModel

BackoffStrategy = Literal["exponential", "exponential_jitter", "full_jitter"]


def _coerce_float(value: Any | None, *, allow_none: bool = True) -> float | None:
    if value is None:
        return None if allow_none else 0.0
    if isinstance(value, (float, int)):
        return float(value)
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None if allow_none else 0.0
        return float(candidate)
    return float(value)


def _coerce_int(value: Any | None, *, allow_none: bool = True) -> int | None:
    if value is None:
        return None if allow_none else 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):  # pragma: no cover - defensive
        return int(value)
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None if allow_none else 0
        return int(float(candidate))
    return int(value)


def _normalize_tags(values: list[Any] | None) -> list[str]:
    if not values:
        return []
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
    return sanitized


class RetryBackoffConfig(BaseModel):
    strategy: BackoffStrategy = Field(default="exponential_jitter")
    base_seconds: float = Field(default=1.5, gt=0)
    max_seconds: float = Field(default=30.0, gt=0)
    jitter_ratio: float = Field(default=0.5, ge=0.0, le=1.0)
    retry_on_assertions: bool = Field(default=False)
    cooldown_seconds: float = Field(default=30.0, gt=0)

    @field_validator("base_seconds", "max_seconds", "cooldown_seconds", mode="before")
    @classmethod
    def _coerce_positive_float(cls, value: Any) -> float:
        result = _coerce_float(value, allow_none=False)
        if result is None or result <= 0:
            raise ValueError("Value must be greater than zero")
        return result

    @field_validator("jitter_ratio", mode="before")
    @classmethod
    def _coerce_jitter(cls, value: Any) -> float:
        result = _coerce_float(value, allow_none=False)
        if result is None:
            return 0.0
        if result < 0:
            return 0.0
        if result > 1:
            return 1.0
        return result

    @model_validator(mode="after")
    def _validate_relationships(self) -> "RetryBackoffConfig":
        if self.max_seconds < self.base_seconds:
            raise ValueError("max_seconds must be greater than or equal to base_seconds")
        return self


class ExecutionPolicyBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    max_concurrency: int | None = Field(default=None, ge=0)
    per_host_qps: float | None = Field(default=None, ge=0.0)
    queue_id: UUID | None = None
    priority: int = Field(default=5, ge=0, le=9)
    retry_max_attempts: int = Field(default=3, ge=1, le=10)
    retry_backoff: RetryBackoffConfig = Field(default_factory=RetryBackoffConfig)
    timeout_seconds: float = Field(default=30.0, ge=0.1)
    circuit_breaker_threshold: int = Field(default=5, ge=0)
    circuit_breaker_window_seconds: int = Field(default=60, ge=1)
    tags_include: list[str] = Field(default_factory=list)
    tags_exclude: list[str] = Field(default_factory=list)
    enabled: bool = Field(default=True)

    @field_validator("per_host_qps", mode="before")
    @classmethod
    def _coerce_qps(cls, value: Any) -> float | None:
        result = _coerce_float(value)
        if result is None or result <= 0:
            return None
        return result

    @field_validator("max_concurrency", mode="before")
    @classmethod
    def _coerce_concurrency(cls, value: Any) -> int | None:
        result = _coerce_int(value)
        if result is None or result <= 0:
            return None
        return result

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def _coerce_timeout(cls, value: Any) -> float:
        result = _coerce_float(value, allow_none=False)
        if result is None or result <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        return result

    @field_validator("circuit_breaker_threshold", mode="before")
    @classmethod
    def _coerce_threshold(cls, value: Any) -> int:
        result = _coerce_int(value, allow_none=False)
        if result is None or result < 0:
            raise ValueError("circuit_breaker_threshold must be non-negative")
        return result

    @field_validator("circuit_breaker_window_seconds", mode="before")
    @classmethod
    def _coerce_window(cls, value: Any) -> int:
        result = _coerce_int(value, allow_none=False)
        if result is None or result <= 0:
            raise ValueError("circuit_breaker_window_seconds must be greater than zero")
        return result

    @field_validator("tags_include", "tags_exclude", mode="before")
    @classmethod
    def _normalize_tag_lists(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if isinstance(value, (set, tuple)):
            value = list(value)
        if not isinstance(value, list):
            raise ValueError("Tags must be provided as a list")
        return _normalize_tags(value)

    @model_validator(mode="after")
    def _ensure_tag_disjoint(self) -> "ExecutionPolicyBase":
        include_keys = {item.lower() for item in self.tags_include}
        exclude_keys = {item.lower() for item in self.tags_exclude}
        if include_keys & exclude_keys:
            raise ValueError("tags_include and tags_exclude cannot overlap")
        return self


class ExecutionPolicyCreate(ExecutionPolicyBase):
    set_default: bool = Field(default=False)


class ExecutionPolicyUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    max_concurrency: int | None = Field(default=None, ge=0)
    per_host_qps: float | None = Field(default=None, ge=0.0)
    queue_id: UUID | None = None
    priority: int | None = Field(default=None, ge=0, le=9)
    retry_max_attempts: int | None = Field(default=None, ge=1, le=10)
    retry_backoff: RetryBackoffConfig | None = None
    timeout_seconds: float | None = Field(default=None, ge=0.1)
    circuit_breaker_threshold: int | None = Field(default=None, ge=0)
    circuit_breaker_window_seconds: int | None = Field(default=None, ge=1)
    tags_include: list[str] | None = None
    tags_exclude: list[str] | None = None
    enabled: bool | None = None
    set_default: bool | None = None

    @field_validator("per_host_qps", mode="before")
    @classmethod
    def _coerce_qps(cls, value: Any) -> float | None:
        result = _coerce_float(value)
        if result is None or result <= 0:
            return None
        return result

    @field_validator("max_concurrency", mode="before")
    @classmethod
    def _coerce_concurrency(cls, value: Any) -> int | None:
        result = _coerce_int(value)
        if result is None or result <= 0:
            return None
        return result

    @field_validator("tags_include", "tags_exclude", mode="before")
    @classmethod
    def _normalize_tags_optional(cls, value: Any) -> list[str] | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = [value]
        if isinstance(value, (set, tuple)):
            value = list(value)
        if not isinstance(value, list):
            raise ValueError("Tags must be provided as a list")
        return _normalize_tags(value)


class ExecutionPolicyRead(IdentifierModel, ORMModel):
    project_id: UUID
    name: str
    max_concurrency: int | None
    per_host_qps: float | None
    queue_id: UUID | None
    priority: int
    retry_max_attempts: int
    retry_backoff: RetryBackoffConfig
    timeout_seconds: float
    circuit_breaker_threshold: int
    circuit_breaker_window_seconds: int
    tags_include: list[str]
    tags_exclude: list[str]
    enabled: bool
    is_default: bool
    default_environment_ids: list[UUID] = Field(default_factory=list)


class ExecutionPolicyTemplateRead(ORMModel):
    key: str
    name: str
    description: str
    policy: ExecutionPolicyBase


class ExecutionPolicyEffectiveRead(ORMModel):
    source: Literal["explicit", "override", "environment", "project", "fallback"]
    policy_id: UUID | None
    policy_name: str
    snapshot: dict[str, Any]


__all__ = [
    "BackoffStrategy",
    "RetryBackoffConfig",
    "ExecutionPolicyBase",
    "ExecutionPolicyCreate",
    "ExecutionPolicyUpdate",
    "ExecutionPolicyRead",
    "ExecutionPolicyTemplateRead",
    "ExecutionPolicyEffectiveRead",
]
