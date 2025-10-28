from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, HttpUrl, model_validator

from app.schemas.common import ORMModel


class ImportSummary(ORMModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    details: list[str] = Field(default_factory=list)


class OpenAPIImportRequest(BaseModel):
    url: HttpUrl | None = None
    spec: dict[str, Any] | None = Field(default=None, alias="json")
    dry_run: bool = False

    @model_validator(mode="after")
    def ensure_payload(cls, values: "OpenAPIImportRequest") -> "OpenAPIImportRequest":  # type: ignore[override]
        if not values.url and values.spec is None:
            raise ValueError("Either 'url' or 'json' must be provided")
        return values


class OpenAPIImportResponse(ORMModel):
    summary: ImportSummary


class PostmanImportRequest(BaseModel):
    collection: dict[str, Any] | None = None
    dry_run: bool = False

    @model_validator(mode="after")
    def ensure_collection(cls, values: "PostmanImportRequest") -> "PostmanImportRequest":  # type: ignore[override]
        if values.collection is None:
            raise ValueError("A Postman v2 collection payload must be provided")
        return values


class PostmanImportResponse(ORMModel):
    summary: ImportSummary
