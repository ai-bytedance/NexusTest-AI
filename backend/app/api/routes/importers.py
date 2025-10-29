from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import ProjectContext, require_project_member
from app.core.errors import ErrorCode, http_exception
from app.db.session import get_db
from app.models.import_source import ImportRun, ImportSource, ImportSourceType, ImporterKind
from app.schemas.importers import (
    ImportPreviewResponse,
    ImportResyncRequest,
    ImportSummary,
    OpenAPIImportOptions,
    OpenAPIImportRequest,
    OpenAPIImportResponse,
    PostmanImportOptions,
    PostmanImportResponse,
)
from app.services.importers import (
    fetch_openapi_spec,
    fetch_postman_collection,
    import_openapi_spec,
    import_postman_collection,
    resync_import_source,
)
from app.services.importers.common import compute_hash

router = APIRouter(prefix="/projects/{project_id}/import", tags=["importers"])


def _parse_postman_options(raw: Any) -> PostmanImportOptions:
    if raw is None:
        return PostmanImportOptions()
    if isinstance(raw, PostmanImportOptions):
        return raw
    if isinstance(raw, dict):
        return PostmanImportOptions(**raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise http_exception(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.IMPORT_INVALID_SPEC,
                "Postman options must be valid JSON",
            ) from exc
        if not isinstance(parsed, dict):
            raise http_exception(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.IMPORT_INVALID_SPEC,
                "Postman options must be an object",
            )
        return PostmanImportOptions(**parsed)
    raise http_exception(
        status.HTTP_400_BAD_REQUEST,
        ErrorCode.IMPORT_INVALID_SPEC,
        "Unsupported options payload type",
    )


def _resolve_import_source(
    db: Session,
    project_id: UUID,
    request: ImportResyncRequest,
) -> ImportSource:
    if request.source_id:
        source = db.execute(
            select(ImportSource).where(
                ImportSource.id == request.source_id,
                ImportSource.project_id == project_id,
                ImportSource.is_deleted.is_(False),
            )
        ).scalar_one_or_none()
        if not source:
            raise http_exception(
                status.HTTP_404_NOT_FOUND,
                ErrorCode.NOT_FOUND,
                "Import source not found",
            )
        return source

    stmt = (
        select(ImportSource)
        .where(
            ImportSource.project_id == project_id,
            ImportSource.is_deleted.is_(False),
        )
        .order_by(ImportSource.updated_at.desc())
    )
    if request.importer is not None:
        stmt = stmt.where(ImportSource.importer == request.importer)

    source = db.execute(stmt).scalars().first()
    if not source:
        raise http_exception(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.NOT_FOUND,
            "No import sources available for project",
        )
    return source



@router.post("/openapi", response_model=ResponseEnvelope)
def import_openapi_specification(
    payload: OpenAPIImportRequest,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    options = payload.options or OpenAPIImportOptions()
    document: dict[str, Any]
    base_url: str | None = None
    source_type: ImportSourceType
    location: str

    if payload.spec is not None:
        if not isinstance(payload.spec, dict):
            raise http_exception(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.IMPORT_INVALID_SPEC,
                "OpenAPI specification must be an object",
            )
        document = payload.spec
        source_type = ImportSourceType.RAW
        location = f"raw:{compute_hash(document)[:12]}"
    else:
        assert payload.url is not None
        try:
            document, fetched_url = fetch_openapi_spec(str(payload.url))
        except ValueError as exc:
            raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.IMPORT_RESOLVE_FAILED, str(exc)) from exc
        source_type = ImportSourceType.URL
        location = str(payload.url)
        base_url = fetched_url

    summary = import_openapi_spec(
        db,
        context.project,
        document,
        options=options,
        source_type=source_type,
        location=location,
        dry_run=payload.dry_run,
        base_url=base_url,
    )
    response = OpenAPIImportResponse(summary=summary)
    return success_response(response)


@router.post("/postman", response_model=ResponseEnvelope)
async def import_postman_collection_endpoint(
    request: Request,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    dry_run = request.query_params.get("dry_run", "false").lower() == "true"
    collection_data: dict[str, Any] | None = None
    source_type: ImportSourceType = ImportSourceType.RAW
    location: str | None = None
    options: PostmanImportOptions = PostmanImportOptions()
    url_value: str | None = None

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        dry_run_value = form.get("dry_run")
        if isinstance(dry_run_value, str):
            dry_run = dry_run_value.lower() == "true"
        options = _parse_postman_options(form.get("options"))
        url_candidate = form.get("url") or form.get("collection_url")
        if isinstance(url_candidate, str) and url_candidate:
            url_value = url_candidate
        file_field = form.get("file")
        if isinstance(file_field, UploadFile):
            raw_bytes = await file_field.read()
            try:
                collection_data = json.loads(raw_bytes.decode())
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise http_exception(
                    status.HTTP_400_BAD_REQUEST,
                    ErrorCode.IMPORT_INVALID_SPEC,
                    "Invalid Postman collection file",
                ) from exc
            source_type = ImportSourceType.FILE
            hash_suffix = compute_hash(collection_data)[:12] if isinstance(collection_data, dict) else ""
            filename = file_field.filename or "upload"
            location = f"file:{filename}:{hash_suffix}" if hash_suffix else f"file:{filename}"
        elif form.get("collection"):
            try:
                collection_data = json.loads(str(form.get("collection")))
            except json.JSONDecodeError as exc:
                raise http_exception(
                    status.HTTP_400_BAD_REQUEST,
                    ErrorCode.IMPORT_INVALID_SPEC,
                    "Invalid Postman collection payload",
                ) from exc
            source_type = ImportSourceType.RAW
        elif url_value is None:
            raise http_exception(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.IMPORT_INVALID_SPEC,
                "Either a Postman collection file, JSON payload, or URL must be provided",
            )
    else:
        try:
            payload = await request.json()
        except json.JSONDecodeError as exc:
            raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.IMPORT_INVALID_SPEC, "Invalid JSON payload") from exc

        if not isinstance(payload, dict):
            raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.IMPORT_INVALID_SPEC, "Invalid JSON payload")

        dry_run = bool(payload.get("dry_run", dry_run))
        options = _parse_postman_options(payload.get("options"))
        url_candidate = payload.get("url") or payload.get("collection_url")
        if isinstance(url_candidate, str) and url_candidate:
            url_value = url_candidate

        collection_candidate = payload.get("collection")
        if collection_candidate is None and {"info", "item"}.issubset(payload.keys()):
            collection_candidate = payload
        if collection_candidate is not None:
            if not isinstance(collection_candidate, dict):
                raise http_exception(
                    status.HTTP_400_BAD_REQUEST,
                    ErrorCode.IMPORT_INVALID_SPEC,
                    "Collection must be an object",
                )
            collection_data = collection_candidate
            source_type = ImportSourceType.RAW

    if url_value:
        try:
            collection_data = fetch_postman_collection(url_value)
        except ValueError as exc:
            raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.IMPORT_RESOLVE_FAILED, str(exc)) from exc
        source_type = ImportSourceType.URL
        location = url_value

    if collection_data is None:
        raise http_exception(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.IMPORT_INVALID_SPEC,
            "Postman collection data is required",
        )
    if not isinstance(collection_data, dict):
        raise http_exception(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.IMPORT_INVALID_SPEC,
            "Postman collection must be a JSON object",
        )

    if location is None:
        hash_suffix = compute_hash(collection_data)[:12]
        location = f"raw:{hash_suffix}"

    summary = import_postman_collection(
        db,
        context.project,
        collection_data,
        options=options,
        source_type=source_type,
        location=location,
        dry_run=dry_run,
    )
    response = PostmanImportResponse(summary=summary)
    return success_response(response)


@router.post("/resync", response_model=ResponseEnvelope)
def resync_imports(
    payload: ImportResyncRequest,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    source = _resolve_import_source(db, context.project.id, payload)
    summary = resync_import_source(db, context.project, source, dry_run=payload.dry_run)
    response = ImportPreviewResponse(summary=summary)
    return success_response(response)


@router.get("/preview", response_model=ResponseEnvelope)
def get_import_preview(
    run_id: UUID = Query(..., alias="id"),
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    run = db.execute(
        select(ImportRun).where(
            ImportRun.id == run_id,
            ImportRun.project_id == context.project.id,
            ImportRun.is_deleted.is_(False),
        )
    ).scalar_one_or_none()
    if not run:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Import run not found")

    summary_payload = dict(run.summary or {})
    summary_payload.setdefault("created", 0)
    summary_payload.setdefault("updated", 0)
    summary_payload.setdefault("skipped", 0)
    summary_payload.setdefault("removed", 0)
    summary_payload.setdefault("details", [])
    summary_payload["dry_run"] = bool(summary_payload.get("dry_run", run.dry_run))
    summary_payload["run_id"] = run.id
    summary_payload["source_id"] = run.source_id
    summary_payload["items"] = run.diff or []

    summary = ImportSummary.model_validate(summary_payload)
    response = ImportPreviewResponse(summary=summary)
    return success_response(response)
