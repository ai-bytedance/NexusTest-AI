from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class RateLimitRule(BaseModel):
    per_minute: int | None = Field(default=None, ge=1)
    per_hour: int | None = Field(default=None, ge=1)
    burst: int | None = Field(default=None, ge=1)
    path_patterns: list[str] = Field(default_factory=lambda: ["*"])
    methods: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize(self) -> "RateLimitRule":
        if not any([self.per_minute, self.per_hour, self.burst]):
            raise ValueError("At least one limit must be provided")
        normalized_patterns: list[str] = []
        for pattern in self.path_patterns or ["*"]:
            value = pattern.strip() or "*"
            if not value.startswith("/") and value != "*":
                value = "/" + value
            normalized_patterns.append(value)
        self.path_patterns = normalized_patterns or ["*"]
        self.methods = [method.upper() for method in self.methods if method]
        return self


class RateLimitPolicyBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    rules: list[RateLimitRule]
    enabled: bool = True

    @model_validator(mode="after")
    def ensure_rules(self) -> "RateLimitPolicyBase":
        if not self.rules:
            raise ValueError("At least one rule is required")
        return self


class RateLimitPolicyCreate(RateLimitPolicyBase):
    pass


class RateLimitPolicyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    rules: list[RateLimitRule] | None = None
    enabled: bool | None = None


class RateLimitPolicyRead(BaseModel):
    id: UUID
    project_id: UUID | None
    name: str
    rules: list[RateLimitRule]
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
    }

    @model_validator(mode="before")
    @classmethod
    def normalize_rules(cls, values: Any) -> Any:
        if isinstance(values, dict) and "rules" in values and not isinstance(values["rules"], list):
            raise ValueError("rules must be a list")
        return values


class RateLimitPolicyDefaultUpdate(BaseModel):
    policy_id: UUID | None


class EffectiveRateLimit(BaseModel):
    project_id: UUID
    default_policy: RateLimitPolicyRead | None
    token_policy: RateLimitPolicyRead | None
    active_rules: list[RateLimitRule]


__all__ = [
    "RateLimitRule",
    "RateLimitPolicyCreate",
    "RateLimitPolicyUpdate",
    "RateLimitPolicyRead",
    "RateLimitPolicyDefaultUpdate",
    "EffectiveRateLimit",
]
