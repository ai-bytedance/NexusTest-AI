from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import IdentifierModel, ORMModel


class RetryBackoffConfig(BaseModel):
    base_seconds: float = Field(default=1.5, gt=0)
    max_seconds: float = Field(default=30.0, gt=0)
    jitter_ratio: float = Field(default=0.5, ge=0.0, le=1.0)
    retry_on_assertions: bool = Field(default=False)
    cooldown_seconds: float = Field(default=30.0, gt=0)

    @field_validator("base_seconds", "max_seconds", "cooldown_seconds", mode="before")
    @classmethod
    def _coerce_float(cls, value: float | int | str) -> float:
        if value is None:
            raise ValueError("Value must be provided")
        return float(value)

    @field_validator("jitter_ratio", mode="before")
    @classmethod
    def _coerce_jitter(cls, value: float | int | str) -> float:
        if value is None:
            return 0.0
        return float(value)

    @model_validator(mode="after")
    def _validate_relationships(self) -> "RetryBackoffConfig":
        if self.max_seconds < self.base_seconds:
            raise ValueError("max_seconds must be greater than or equal to base_seconds")
        return self


class ExecutionPolicyBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    max_concurrency: int | None = Field(default=None, ge=0)
    per_host_qps: float | None = Field(default=None, ge=0.0)
    retry_max_attempts: int = Field(default=3, ge=1, le=5)
    retry_backoff: RetryBackoffConfig = Field(default_factory=RetryBackoffConfig)
    timeout_seconds: int = Field(default=30, ge=1)
    circuit_breaker_threshold: int = Field(default=5, ge=1)
    enabled: bool = Field(default=True)

    @field_validator("per_host_qps", mode="before")
    @classmethod
    def _coerce_qps(cls, value: Any) -> float | None:
        if value in (None, "", "null"):
            return None
        return float(value)

    @field_validator("max_concurrency", mode="before")
    @classmethod
    def _coerce_concurrency(cls, value: Any) -> int | None:
        if value in (None, "", "null"):
            return None
        return int(value)


class ExecutionPolicyCreate(ExecutionPolicyBase):
    set_default: bool = Field(default=False)


class ExecutionPolicyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    max_concurrency: int | None = Field(default=None, ge=0)
    per_host_qps: float | None = Field(default=None, ge=0.0)
    retry_max_attempts: int | None = Field(default=None, ge=1, le=5)
    retry_backoff: RetryBackoffConfig | None = None
    timeout_seconds: int | None = Field(default=None, ge=1)
    circuit_breaker_threshold: int | None = Field(default=None, ge=1)
    enabled: bool | None = None
    set_default: bool | None = None

    @field_validator("per_host_qps", mode="before")
    @classmethod
    def _coerce_qps(cls, value: Any) -> float | None:
        if value in (None, "", "null"):
            return None
        return float(value)

    @field_validator("max_concurrency", mode="before")
    @classmethod
    def _coerce_concurrency(cls, value: Any) -> int | None:
        if value in (None, "", "null"):
            return None
        return int(value)


class ExecutionPolicyRead(IdentifierModel, ORMModel):
    project_id: UUID
    name: str
    max_concurrency: int | None
    per_host_qps: float | None
    retry_max_attempts: int
    retry_backoff: RetryBackoffConfig
    timeout_seconds: int
    circuit_breaker_threshold: int
    enabled: bool
    is_default: bool


__all__ = [
    "RetryBackoffConfig",
    "ExecutionPolicyBase",
    "ExecutionPolicyCreate",
    "ExecutionPolicyUpdate",
    "ExecutionPolicyRead",
]
