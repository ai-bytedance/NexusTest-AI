from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, model_validator

from app.models.import_source import ImportApprovalDecision, ImportRunStatus, ImporterKind
from app.schemas.common import ORMModel


class ImportChangeType(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    SKIPPED = "skipped"
    REMOVED = "removed"


class ImportChange(ORMModel):
    change_type: ImportChangeType
    method: str
    path: str
    normalized_path: str
    version: str
    name: str
    api_id: UUID | None = None
    summary: str | None = None
    diff: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImportSummary(ORMModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    removed: int = 0
    dry_run: bool = False
    run_id: UUID | None = None
    source_id: UUID | None = None
    details: list[str] = Field(default_factory=list)
    items: list[ImportChange] = Field(default_factory=list)


class OpenAPIImportOptions(BaseModel):
    server: str | int | None = None
    server_variables: dict[str, str] = Field(default_factory=dict)
    include_tags: list[str] | None = None
    exclude_tags: list[str] | None = None
    environment: dict[str, str] = Field(default_factory=dict)
    resolve_remote_refs: bool = True
    preserve_vendor_extensions: bool = True
    schedule_plan_id: UUID | None = None
    prefer_server: str | None = None


class OpenAPIImportRequest(BaseModel):
    url: HttpUrl | None = None
    spec: dict[str, Any] | None = Field(default=None, alias="json")
    dry_run: bool = False
    options: OpenAPIImportOptions | None = None

    @model_validator(mode="after")
    def ensure_payload(cls, values: "OpenAPIImportRequest") -> "OpenAPIImportRequest":  # type: ignore[override]
        if not values.url and values.spec is None:
            raise ValueError("Either 'url' or 'json' must be provided")
        return values


class OpenAPIImportResponse(ORMModel):
    summary: ImportSummary


class PostmanImportOptions(BaseModel):
    environment: dict[str, Any] = Field(default_factory=dict)
    globals: dict[str, Any] = Field(default_factory=dict)
    resolve_variables: bool = True
    inherit_auth: bool = True
    capture_scripts: bool = True
    schedule_plan_id: UUID | None = None


class PostmanImportRequest(BaseModel):
    collection: dict[str, Any] | None = None
    url: HttpUrl | None = None
    dry_run: bool = False
    options: PostmanImportOptions | None = None

    @model_validator(mode="after")
    def ensure_collection(cls, values: "PostmanImportRequest") -> "PostmanImportRequest":  # type: ignore[override]
        if values.collection is None and values.url is None:
            raise ValueError("Either a Postman collection payload or URL must be provided")
        return values


class PostmanImportResponse(ORMModel):
    summary: ImportSummary


class ImportResyncRequest(BaseModel):
    source_id: UUID | None = None
    importer: ImporterKind | None = None
    dry_run: bool = False


class ImportPreviewResponse(ORMModel):
    summary: ImportSummary


class OpenAPIImportPrepareRequest(OpenAPIImportRequest):
    importer: Literal[ImporterKind.OPENAPI] = Field(default=ImporterKind.OPENAPI)
    source_id: UUID | None = None


class PostmanImportPrepareRequest(PostmanImportRequest):
    importer: Literal[ImporterKind.POSTMAN] = Field(default=ImporterKind.POSTMAN)
    source_id: UUID | None = None


ImportPreparePayload = OpenAPIImportPrepareRequest | PostmanImportPrepareRequest

ImportPrepareRequest = Annotated[
    ImportPreparePayload,
    Field(discriminator="importer"),
]


class ImportApproveRequest(BaseModel):
    comment: str | None = None


class ImportRollbackRequest(BaseModel):
    comment: str | None = None


class ImportApprovalRecord(ORMModel):
    id: UUID
    approver_id: UUID
    decision: ImportApprovalDecision
    comment: str | None = None
    created_at: datetime


class ImportRunInfo(ORMModel):
    id: UUID
    project_id: UUID
    source_id: UUID | None
    importer: ImporterKind
    status: ImportRunStatus
    dry_run: bool
    summary: ImportSummary
    created_at: datetime
    created_by: UUID
    applied_at: datetime | None = None
    applied_by_id: UUID | None = None
    rolled_back_at: datetime | None = None
    rolled_back_by_id: UUID | None = None


class ImportRunDetail(ImportRunInfo):
    diff: list[ImportChange] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    approvals: list[ImportApprovalRecord] = Field(default_factory=list)


class ImportRunListResponse(ORMModel):
    runs: list[ImportRunInfo] = Field(default_factory=list)


__all__ = [
    "ImportChangeType",
    "ImportChange",
    "ImportSummary",
    "OpenAPIImportOptions",
    "OpenAPIImportRequest",
    "OpenAPIImportResponse",
    "PostmanImportOptions",
    "PostmanImportRequest",
    "PostmanImportResponse",
    "ImportResyncRequest",
    "ImportPreviewResponse",
    "OpenAPIImportPrepareRequest",
    "PostmanImportPrepareRequest",
    "ImportPreparePayload",
    "ImportPrepareRequest",
    "ImportApproveRequest",
    "ImportRollbackRequest",
    "ImportApprovalRecord",
    "ImportRunInfo",
    "ImportRunDetail",
    "ImportRunListResponse",
]
