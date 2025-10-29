from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ErrorCode, http_exception
from app.models.import_source import ImportSource, ImportSourceType, ImporterKind
from app.models.project import Project
from app.schemas.importers import ImportSummary, OpenAPIImportOptions, PostmanImportOptions
from app.services.importers.openapi_importer import fetch_openapi_spec, import_openapi_spec
from app.services.importers.postman_importer import fetch_postman_collection, import_postman_collection


def resync_import_source(
    db: Session,
    project: Project,
    source: ImportSource,
    *,
    dry_run: bool = False,
) -> ImportSummary:
    if source.project_id != project.id:
        raise http_exception(
            status_code=404,
            code=ErrorCode.NOT_FOUND,
            message="Import source not found for project",
        )

    if source.importer == ImporterKind.OPENAPI:
        return _resync_openapi(db, project, source, dry_run=dry_run)
    if source.importer == ImporterKind.POSTMAN:
        return _resync_postman(db, project, source, dry_run=dry_run)

    raise http_exception(
        status_code=400,
        code=ErrorCode.IMPORT_INVALID_SPEC,
        message=f"Unsupported importer type: {source.importer}",
    )


def _resync_openapi(
    db: Session,
    project: Project,
    source: ImportSource,
    *,
    dry_run: bool,
) -> ImportSummary:
    options_data = source.options or {}
    openapi_options = OpenAPIImportOptions(**options_data) if options_data else OpenAPIImportOptions()

    document: dict[str, Any]
    base_url: str | None = None

    if source.source_type == ImportSourceType.URL:
        if not source.location:
            raise http_exception(
                status_code=400,
                code=ErrorCode.IMPORT_INVALID_SPEC,
                message="Import source is missing a URL location",
            )
        document, base_url = fetch_openapi_spec(source.location)
    else:
        if not isinstance(source.payload_snapshot, dict):
            raise http_exception(
                status_code=400,
                code=ErrorCode.IMPORT_INVALID_SPEC,
                message="Stored OpenAPI payload is unavailable",
            )
        document = source.payload_snapshot
        if isinstance(source.metadata, dict):
            base_url = source.metadata.get("base_url")

    return import_openapi_spec(
        db,
        project,
        document,
        options=openapi_options,
        source_type=source.source_type,
        location=source.location,
        dry_run=dry_run,
        base_url=base_url,
        existing_source=source,
    )


def _resync_postman(
    db: Session,
    project: Project,
    source: ImportSource,
    *,
    dry_run: bool,
) -> ImportSummary:
    options_data = source.options or {}
    postman_options = PostmanImportOptions(**options_data) if options_data else PostmanImportOptions()

    collection: dict[str, Any]
    if source.source_type == ImportSourceType.URL:
        if not source.location:
            raise http_exception(
                status_code=400,
                code=ErrorCode.IMPORT_INVALID_SPEC,
                message="Import source is missing a URL location",
            )
        try:
            collection = fetch_postman_collection(source.location)
        except ValueError as exc:
            raise http_exception(
                status_code=400,
                code=ErrorCode.IMPORT_RESOLVE_FAILED,
                message=str(exc),
            ) from exc
    else:
        if not isinstance(source.payload_snapshot, dict):
            raise http_exception(
                status_code=400,
                code=ErrorCode.IMPORT_INVALID_SPEC,
                message="Stored Postman collection snapshot is unavailable",
            )
        collection = source.payload_snapshot

    return import_postman_collection(
        db,
        project,
        collection,
        options=postman_options,
        source_type=source.source_type,
        location=source.location,
        dry_run=dry_run,
        existing_source=source,
    )

