from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field, field_validator

from app.models.integration import IntegrationProvider
from app.schemas.common import IdentifierModel, ORMModel


class IntegrationBase(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    provider: IntegrationProvider
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class IntegrationCreate(IntegrationBase):
    test_connection: bool = True


class IntegrationUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    config: dict[str, Any] | None = None
    enabled: bool | None = None
    test_connection: bool | None = None

    @field_validator("test_connection", mode="before")
    @classmethod
    def _normalize_test_flag(cls, value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() not in {"0", "false", "no"}
        return bool(value)


class IntegrationRead(IdentifierModel):
    project_id: UUID
    name: str
    provider: IntegrationProvider
    config: dict[str, Any]
    enabled: bool
    created_by: UUID


class IntegrationConnectionStatus(ORMModel):
    ok: bool
    details: dict[str, Any] | None = None


__all__ = [
    "IntegrationBase",
    "IntegrationCreate",
    "IntegrationUpdate",
    "IntegrationRead",
    "IntegrationConnectionStatus",
]
