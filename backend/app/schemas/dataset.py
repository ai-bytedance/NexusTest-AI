from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from app.models.dataset import DatasetType
from app.schemas.common import IdentifierModel, ORMModel


class DatasetBase(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    type: DatasetType
    schema: dict[str, Any] = Field(default_factory=dict)


class DatasetCreate(DatasetBase):
    source: dict[str, Any] | None = None


class DatasetUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    type: DatasetType | None = None
    schema: dict[str, Any] | None = None
    source: dict[str, Any] | None = None


class DatasetRead(IdentifierModel):
    project_id: UUID
    name: str
    type: DatasetType
    schema: dict[str, Any]
    source: dict[str, Any]
    created_by: UUID


class DatasetPreview(ORMModel):
    dataset_id: UUID
    rows: list[dict[str, Any]]
    total_rows: int | None = None


__all__ = [
    "DatasetType",
    "DatasetBase",
    "DatasetCreate",
    "DatasetUpdate",
    "DatasetRead",
    "DatasetPreview",
]
