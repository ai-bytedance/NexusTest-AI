from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import ProjectContext, require_project_member
from app.core.errors import ErrorCode, http_exception
from app.db.session import get_db
from app.schemas.importers import (
    OpenAPIImportRequest,
    OpenAPIImportResponse,
    PostmanImportResponse,
)
from app.services.importers.openapi_importer import (
    fetch_openapi_spec,
    import_openapi_spec,
)
from app.services.importers.postman_importer import import_postman_collection

router = APIRouter(prefix="/projects/{project_id}/import", tags=["importers"])


@router.post("/openapi", response_model=ResponseEnvelope)
def import_openapi_specification(
    payload: OpenAPIImportRequest,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    document: dict[str, Any]
    if payload.spec is not None:
        if not isinstance(payload.spec, dict):
            raise http_exception(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.BAD_REQUEST,
                "OpenAPI specification must be an object",
            )
        document = payload.spec
    else:
        try:
            document = fetch_openapi_spec(str(payload.url))
        except ValueError as exc:
            raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, str(exc)) from exc

    summary = import_openapi_spec(db, context.project, document, dry_run=payload.dry_run)
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

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        dry_run_value = form.get("dry_run")
        if isinstance(dry_run_value, str):
            dry_run = dry_run_value.lower() == "true"
        file_field = form.get("file")
        if isinstance(file_field, UploadFile):
            raw_bytes = await file_field.read()
            try:
                collection_data = json.loads(raw_bytes.decode())
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise http_exception(
                    status.HTTP_400_BAD_REQUEST,
                    ErrorCode.BAD_REQUEST,
                    "Invalid Postman collection file",
                ) from exc
        elif form.get("collection"):
            try:
                collection_data = json.loads(str(form.get("collection")))
            except json.JSONDecodeError as exc:
                raise http_exception(
                    status.HTTP_400_BAD_REQUEST,
                    ErrorCode.BAD_REQUEST,
                    "Invalid Postman collection payload",
                ) from exc
    else:
        try:
            payload = await request.json()
        except json.JSONDecodeError as exc:
            raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "Invalid JSON payload") from exc

        if not isinstance(payload, dict):
            raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "Invalid JSON payload")
        dry_run = bool(payload.get("dry_run", dry_run))
        collection_candidate = payload.get("collection") or payload
        if not isinstance(collection_candidate, dict):
            raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "Collection must be an object")
        collection_data = collection_candidate

    if collection_data is None:
        raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "Postman collection data is required")

    summary = import_postman_collection(db, context.project, collection_data, dry_run=dry_run)
    response = PostmanImportResponse(summary=summary)
    return success_response(response)
