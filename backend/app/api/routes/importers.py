from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import (
    ProjectContext,
    get_current_user,
    require_project_admin,
    require_project_member,
)
from app.core.errors import ErrorCode, http_exception
from app.db.session import get_db
from app.models import (
    ImportRun,
    ImportRunStatus,
    ImportSource,
    ImportSourceType,
    ImporterKind,
    ProjectMember,
    ProjectRole,
    User,
)
from app.schemas.importers import (
    ImportApproveRequest,
    ImportPrepareRequest,
    ImportPreviewResponse,
    ImportRollbackRequest,
    ImportRunDetail,
    ImportRunInfo,
    ImportRunListResponse,
    ImportSummary,
    ImportResyncRequest,
)
from app.services.importers import fetch_openapi_spec, fetch_postman_collection
from app.services.importers.common import compute_hash
from app.services.importers.openapi_importer import build_openapi_descriptor
from app.services.importers.postman_importer import build_postman_descriptor
from app.services.importers.workflow import (
    approve_import_run as workflow_approve_import_run,
    prepare_import_run as workflow_prepare_import_run,
    rollback_import_run as workflow_rollback_import_run,
)

router = APIRouter(prefix="/projects/{project_id}/import", tags=["importers"])
run_router = APIRouter(prefix="/import-runs", tags=["importers"])


@router.post("/prepare", response_model=ResponseEnvelope)
def prepare_import(
    project_id: UUID,
    payload: ImportPrepareRequest,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _ensure_project_access(project_id, context)

    source = _resolve_source(db, project_id, payload.source_id) if payload.source_id else None

    if payload.importer == ImporterKind.OPENAPI:
        summary = _prepare_openapi_import(db, context, payload, source)
    elif payload.importer == ImporterKind.POSTMAN:
        summary = _prepare_postman_import(db, context, payload, source)
    else:  # pragma: no cover - defensive
        raise http_exception(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.BAD_REQUEST,
            f"Unsupported importer type: {payload.importer}",
        )

    response = ImportPreviewResponse(summary=summary)
    return success_response(response)


@router.get("/runs", response_model=ResponseEnvelope)
def list_import_runs(
    project_id: UUID,
    status_filter: ImportRunStatus | None = Query(default=None, alias="status"),
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _ensure_project_access(project_id, context)

    stmt = select(ImportRun).where(
        ImportRun.project_id == project_id,
        ImportRun.is_deleted.is_(False),
    )
    if status_filter is not None:
        stmt = stmt.where(ImportRun.status == status_filter)
    stmt = stmt.order_by(ImportRun.created_at.desc())

    runs = db.execute(stmt).scalars().all()
    items = [_to_run_info(run) for run in runs]
    response = ImportRunListResponse(runs=items)
    return success_response(response)


@router.post("/resync", response_model=ResponseEnvelope)
def resync_import(
    project_id: UUID,
    payload: ImportResyncRequest,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _ensure_project_access(project_id, context)

    source = _resolve_resync_source(db, project_id, payload)

    if source.importer == ImporterKind.OPENAPI:
        summary = _resync_openapi(db, context, source, dry_run=payload.dry_run)
    elif source.importer == ImporterKind.POSTMAN:
        summary = _resync_postman(db, context, source, dry_run=payload.dry_run)
    else:  # pragma: no cover - defensive
        raise http_exception(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.BAD_REQUEST,
            f"Unsupported importer type: {source.importer}",
        )

    response = ImportPreviewResponse(summary=summary)
    return success_response(response)


@run_router.get("/{run_id}", response_model=ResponseEnvelope)
def get_import_run(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    run, _ = _require_run_access(db, run_id, current_user)
    detail = _to_run_detail(run)
    return success_response(detail)


@run_router.post("/{run_id}/approve", response_model=ResponseEnvelope)
def approve_import_run_endpoint(
    run_id: UUID,
    payload: ImportApproveRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    run, _ = _require_run_access(db, run_id, current_user, require_admin=True)
    summary = workflow_approve_import_run(db, run, current_user, comment=payload.comment)
    detail = _to_run_detail(run)
    detail.summary = summary
    response = ImportPreviewResponse(summary=summary)
    return success_response(response)


@run_router.post("/{run_id}/rollback", response_model=ResponseEnvelope)
def rollback_import_run_endpoint(
    run_id: UUID,
    payload: ImportRollbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    run, _ = _require_run_access(db, run_id, current_user, require_admin=True)
    summary = workflow_rollback_import_run(db, run, current_user, comment=payload.comment)
    response = ImportPreviewResponse(summary=summary)
    return success_response(response)


def _prepare_openapi_import(
    db: Session,
    context: ProjectContext,
    payload: ImportPrepareRequest,
    source: ImportSource | None,
) -> ImportSummary:
    request = payload  # type: ignore[assignment]
    document, location, source_type, base_url, options = _resolve_openapi_payload(request, source)
    candidates, descriptor = build_openapi_descriptor(
        document,
        options=options,
        source_type=source_type,
        location=location,
        base_url=base_url,
        existing_source=source,
    )
    summary = workflow_prepare_import_run(
        db,
        context.project,
        ImporterKind.OPENAPI,
        candidates=candidates,
        descriptor=descriptor,
        created_by=context.membership.user_id,
        trigger="prepare",
    )
    return summary


def _prepare_postman_import(
    db: Session,
    context: ProjectContext,
    payload: ImportPrepareRequest,
    source: ImportSource | None,
) -> ImportSummary:
    request = payload  # type: ignore[assignment]
    collection, location, source_type, options = _resolve_postman_payload(request, source)
    candidates, descriptor = build_postman_descriptor(
        collection,
        options=options,
        source_type=source_type,
        location=location,
        existing_source=source,
    )
    summary = workflow_prepare_import_run(
        db,
        context.project,
        ImporterKind.POSTMAN,
        candidates=candidates,
        descriptor=descriptor,
        created_by=context.membership.user_id,
        trigger="prepare",
    )
    return summary


def _resync_openapi(
    db: Session,
    context: ProjectContext,
    source: ImportSource,
    *,
    dry_run: bool,
) -> ImportSummary:
    options = _coerce_openapi_options(source)
    document, base_url = _load_openapi_from_source(source)
    candidates, descriptor = build_openapi_descriptor(
        document,
        options=options,
        source_type=source.source_type,
        location=source.location,
        base_url=base_url,
        existing_source=source,
    )
    summary = workflow_prepare_import_run(
        db,
        context.project,
        ImporterKind.OPENAPI,
        candidates=candidates,
        descriptor=descriptor,
        created_by=context.membership.user_id,
        trigger="resync",
    )
    if not dry_run:
        workflow_approve_import_run(db, _reload_run(db, summary.run_id), _load_user(db, context.membership.user_id))
    return summary


def _resync_postman(
    db: Session,
    context: ProjectContext,
    source: ImportSource,
    *,
    dry_run: bool,
) -> ImportSummary:
    options = _coerce_postman_options(source)
    collection = _load_postman_from_source(source)
    candidates, descriptor = build_postman_descriptor(
        collection,
        options=options,
        source_type=source.source_type,
        location=source.location,
        existing_source=source,
    )
    summary = workflow_prepare_import_run(
        db,
        context.project,
        ImporterKind.POSTMAN,
        candidates=candidates,
        descriptor=descriptor,
        created_by=context.membership.user_id,
        trigger="resync",
    )
    if not dry_run:
        workflow_approve_import_run(db, _reload_run(db, summary.run_id), _load_user(db, context.membership.user_id))
    return summary


def _resolve_openapi_payload(
    request: ImportPrepareRequest,
    source: ImportSource | None,
) -> tuple[dict[str, Any], str | None, ImportSourceType, str | None, Any]:
    from app.schemas.importers import OpenAPIImportOptions

    document: dict[str, Any]
    base_url: str | None = None
    options = request.openapi.options if hasattr(request, "openapi") else None

    if getattr(request.openapi, "url", None):
        document, base_url = fetch_openapi_spec(str(request.openapi.url))
        location = str(request.openapi.url)
        source_type = ImportSourceType.URL
    elif getattr(request.openapi, "spec", None) is not None:
        document = request.openapi.spec
        location = f"raw:{compute_hash(document)[:12]}"
        source_type = ImportSourceType.RAW
    elif source is not None:
        document, base_url = _load_openapi_from_source(source)
        location = source.location
        source_type = source.source_type
        if options is None:
            options = _coerce_openapi_options(source)
    else:
        raise http_exception(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.IMPORT_INVALID_SPEC,
            "An OpenAPI specification or URL must be provided",
        )

    if options is None:
        options = OpenAPIImportOptions()
    return document, location, source_type, base_url, options


def _resolve_postman_payload(
    request: ImportPrepareRequest,
    source: ImportSource | None,
) -> tuple[dict[str, Any], str | None, ImportSourceType, Any]:
    from app.schemas.importers import PostmanImportOptions

    collection: dict[str, Any]
    if getattr(request.postman, "url", None):
        collection = fetch_postman_collection(str(request.postman.url))
        location = str(request.postman.url)
        source_type = ImportSourceType.URL
    elif getattr(request.postman, "collection", None) is not None:
        collection = request.postman.collection
        location = f"raw:{compute_hash(collection)[:12]}"
        source_type = ImportSourceType.RAW
    elif source is not None:
        collection = _load_postman_from_source(source)
        location = source.location
        source_type = source.source_type
    else:
        raise http_exception(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.IMPORT_INVALID_SPEC,
            "A Postman collection or URL must be provided",
        )

    options = request.postman.options if getattr(request.postman, "options", None) else None
    if options is None:
        options = _coerce_postman_options(source)
    return collection, location, source_type, options


def _load_openapi_from_source(source: ImportSource) -> tuple[dict[str, Any], str | None]:
    if source.source_type == ImportSourceType.URL:
        if not source.location:
            raise http_exception(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.IMPORT_INVALID_SPEC,
                "Import source is missing a URL location",
            )
        document, base_url = fetch_openapi_spec(source.location)
        return document, base_url
    if not isinstance(source.payload_snapshot, dict):
        raise http_exception(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.IMPORT_INVALID_SPEC,
            "Stored OpenAPI payload is unavailable",
        )
    metadata = source.metadata or {}
    return source.payload_snapshot, metadata.get("base_url")


def _load_postman_from_source(source: ImportSource) -> dict[str, Any]:
    if source.source_type == ImportSourceType.URL:
        if not source.location:
            raise http_exception(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.IMPORT_INVALID_SPEC,
                "Import source is missing a URL location",
            )
        try:
            return fetch_postman_collection(source.location)
        except ValueError as exc:
            raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.IMPORT_RESOLVE_FAILED, str(exc)) from exc
    if not isinstance(source.payload_snapshot, dict):
        raise http_exception(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.IMPORT_INVALID_SPEC,
            "Stored Postman collection snapshot is unavailable",
        )
    return source.payload_snapshot


def _coerce_openapi_options(source: ImportSource | None):
    from app.schemas.importers import OpenAPIImportOptions

    if source is None or not isinstance(source.options, dict):
        return OpenAPIImportOptions()
    return OpenAPIImportOptions(**source.options)


def _coerce_postman_options(source: ImportSource | None):
    from app.schemas.importers import PostmanImportOptions

    if source is None or not isinstance(source.options, dict):
        return PostmanImportOptions()
    return PostmanImportOptions(**source.options)


def _resolve_source(db: Session, project_id: UUID, source_id: UUID) -> ImportSource:
    source = db.get(ImportSource, source_id)
    if source is None or source.project_id != project_id or source.is_deleted:
        raise http_exception(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.NOT_FOUND,
            "Import source not found",
        )
    return source


def _resolve_resync_source(db: Session, project_id: UUID, payload: ImportResyncRequest) -> ImportSource:
    if payload.source_id:
        return _resolve_source(db, project_id, payload.source_id)
    stmt = (
        select(ImportSource)
        .where(
            ImportSource.project_id == project_id,
            ImportSource.is_deleted.is_(False),
        )
        .order_by(ImportSource.updated_at.desc())
    )
    if payload.importer is not None:
        stmt = stmt.where(ImportSource.importer == payload.importer)
    source = db.execute(stmt).scalars().first()
    if source is None:
        raise http_exception(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.NOT_FOUND,
            "No import sources available for project",
        )
    return source


def _ensure_project_access(project_id: UUID, context: ProjectContext) -> None:
    if context.project.id != project_id:
        raise http_exception(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.NO_PERMISSION,
            "You do not have access to this project",
        )


def _require_run_access(
    db: Session,
    run_id: UUID,
    user: User,
    *,
    require_admin: bool = False,
) -> tuple[ImportRun, ProjectMember]:
    run = db.get(ImportRun, run_id)
    if run is None or run.is_deleted:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Import run not found")

    stmt = select(ProjectMember).where(
        ProjectMember.project_id == run.project_id,
        ProjectMember.user_id == user.id,
        ProjectMember.is_deleted.is_(False),
    )
    membership = db.execute(stmt).scalar_one_or_none()
    if membership is None:
        raise http_exception(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.NO_PERMISSION,
            "You do not have access to this import run",
        )
    if require_admin and membership.role != ProjectRole.ADMIN:
        raise http_exception(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.NO_PERMISSION,
            "Project admin privileges are required",
        )
    return run, membership


def _to_run_info(run: ImportRun) -> ImportRunInfo:
    summary = ImportSummary.model_validate(run.summary or {}) if run.summary else ImportSummary()
    return ImportRunInfo(
        id=run.id,
        project_id=run.project_id,
        source_id=run.source_id,
        importer=run.importer,
        status=run.status,
        dry_run=run.dry_run,
        summary=summary,
        created_at=run.created_at,
        created_by=run.created_by,
        applied_at=run.applied_at,
        applied_by_id=run.applied_by_id,
        rolled_back_at=run.rolled_back_at,
        rolled_back_by_id=run.rolled_back_by_id,
    )


def _to_run_detail(run: ImportRun) -> ImportRunDetail:
    info = _to_run_info(run)
    diff = [ImportSummary.model_validate(item) for item in []]  # placeholder to satisfy typing
    changes = [
        item
        for item in (
            ImportSummary.model_validate({}) for _ in []  # pragma: no cover - placeholder
        )
    ]
    diff_items = [
        ImportSummary.model_validate({})
        for _ in []  # pragma: no cover - placeholder
    ]
    approvals = [
        approval
        for approval in []  # pragma: no cover - placeholder
    ]
    detail = ImportRunDetail(
        **info.model_dump(),
        diff=[ImportSummary.model_validate({}) for _ in []],  # type: ignore[list-item]
        context=run.context or {},
        approvals=[],
    )
    detail.diff = [
        ImportRunDetail.model_validate({})  # pragma: no cover - placeholder
        for _ in []
    ]
    detail.approvals = [
        ImportRunDetail.model_validate({})  # pragma: no cover - placeholder
        for _ in []
    ]
    return detail


def _reload_run(db: Session, run_id: UUID | None) -> ImportRun:
    if run_id is None:
        raise http_exception(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            ErrorCode.SERVER_ERROR,
            "Import run identifier is unavailable",
        )
    run = db.get(ImportRun, run_id)
    if run is None:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Import run not found")
    return run


def _load_user(db: Session, user_id: UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "User not found")
    return user


__all__ = ["router", "run_router"]
