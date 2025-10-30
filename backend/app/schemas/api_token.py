from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.api_tokens import ALL_TOKEN_SCOPES


def _unique_scopes(scopes: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in scopes:
        value = str(raw).strip()
        if not value:
            continue
        if value not in ALL_TOKEN_SCOPES:
            raise ValueError(f"Unknown scope: {value}")
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _unique_project_ids(project_ids: list[UUID]) -> list[UUID]:
    seen: set[UUID] = set()
    unique: list[UUID] = []
    for project_id in project_ids:
        if project_id in seen:
            continue
        seen.add(project_id)
        unique.append(project_id)
    return unique


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    scopes: list[str]
    project_ids: list[UUID] = Field(default_factory=list)
    expires_at: datetime | None = None
    rate_limit_policy_id: UUID | None = None

    @model_validator(mode="before")
    @classmethod
    def deduplicate(cls, values: Any) -> Any:
        data = dict(values or {})
        scopes = data.get("scopes") or []
        data["scopes"] = _unique_scopes(list(scopes))
        project_ids = data.get("project_ids") or []
        data["project_ids"] = _unique_project_ids([UUID(str(item)) for item in project_ids])
        return data

    @field_validator("expires_at")
    @classmethod
    def validate_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def ensure_scopes(self) -> "ApiTokenCreate":
        if not self.scopes:
            raise ValueError("At least one scope is required")
        return self


class ApiTokenPatchRequest(BaseModel):
    action: Literal["revoke", "rotate"]


class ApiTokenRead(BaseModel):
    id: UUID
    name: str
    token_prefix: str
    scopes: list[str]
    project_ids: list[UUID]
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    rate_limit_policy_id: UUID | None

    model_config = {
        "from_attributes": True,
    }

    @model_validator(mode="before")
    @classmethod
    def convert_project_ids(cls, values: Any) -> Any:
        if isinstance(values, dict) and "project_ids" in values:
            raw_ids = values.get("project_ids") or []
            values["project_ids"] = [UUID(str(item)) for item in raw_ids]
        return values


class ApiTokenWithSecret(ApiTokenRead):
    token: str


__all__ = [
    "ApiTokenCreate",
    "ApiTokenPatchRequest",
    "ApiTokenRead",
    "ApiTokenWithSecret",
]
