from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode, http_exception
from app.logging import get_logger
from app.models import (
    Api,
    ApiArchive,
    ApiArchiveChangeType,
    ImportApproval,
    ImportApprovalDecision,
    ImportRun,
    ImportRunStatus,
    ImportSource,
    ImportSourceType,
    ImporterKind,
    Project,
    User,
)
from app.schemas.importers import (
    ImportChange,
    ImportChangeType,
    ImportSummary,
)
from app.services.importers.common import (
    ImportCandidate,
    compute_fingerprint,
    compute_hash,
    significant_fields,
)

logger = get_logger()


@dataclass(slots=True)
class SourceDescriptor:
    source_type: ImportSourceType
    location: str | None
    options: dict[str, Any]
    payload_snapshot: dict[str, Any] | None
    metadata: dict[str, Any]
    payload_hash: str
    base_url: str | None = None
    existing: ImportSource | None = None


def prepare_import_run(
    db: Session,
    project: Project,
    importer: ImporterKind,
    *,
    candidates: Iterable[ImportCandidate],
    descriptor: SourceDescriptor,
    created_by: uuid.UUID,
    trigger: str | None = None,
) -> ImportSummary:
    source = _ensure_source(db, project, importer, descriptor)
    summary, changes = _build_diff(db, project, importer, candidates, source)

    now = datetime.now(timezone.utc)
    summary.dry_run = True
    summary.source_id = source.id if source else None

    run_context: dict[str, Any] = {
        "source": {
            "id": str(source.id) if source else None,
            "type": descriptor.source_type.value,
            "location": descriptor.location,
            "options": descriptor.options,
            "metadata": descriptor.metadata,
            "payload_hash": descriptor.payload_hash,
            "payload_snapshot": descriptor.payload_snapshot,
            "base_url": descriptor.base_url,
        },
        "trigger": trigger,
    }

    run = ImportRun(
        project_id=project.id,
        source_id=source.id if source else None,
        importer=importer,
        dry_run=True,
        status=ImportRunStatus.DIFF_READY,
        summary=_serialize_summary(summary),
        diff=[change.model_dump(mode="json") for change in changes],
        context=run_context,
        created_by=created_by,
    )
    db.add(run)
    db.flush()

    summary.run_id = run.id

    if source is not None:
        source.last_prepared_hash = descriptor.payload_hash
        source.last_prepared_at = now
        source.metadata_ = descriptor.metadata or {}
        source.options = descriptor.options or {}
        db.add(source)

    summary.details = _build_details(summary)

    db.commit()
    logger.info(
        "import_run_prepared",
        project_id=str(project.id),
        run_id=str(run.id),
        importer=importer.value,
        created_by=str(created_by),
    )
    return summary


def approve_import_run(
    db: Session,
    run: ImportRun,
    actor: User,
    *,
    comment: str | None = None,
) -> ImportSummary:
    if run.status != ImportRunStatus.DIFF_READY:
        raise http_exception(
            status_code=400,
            code=ErrorCode.BAD_REQUEST,
            message="Import run is not awaiting approval",
        )

    summary = ImportSummary.model_validate(run.summary or {}) if run.summary else ImportSummary()
    changes = [ImportChange.model_validate(item) for item in run.diff or []]

    source = run.source
    if source is None:
        raise http_exception(
            status_code=400,
            code=ErrorCode.BAD_REQUEST,
            message="Import run has no associated source",
        )

    context_source = (run.context or {}).get("source", {})
    payload_hash = context_source.get("payload_hash")

    try:
        archives = _apply_changes(db, run, source, changes, actor)

        now = datetime.now(timezone.utc)
        run.status = ImportRunStatus.APPLIED
        run.dry_run = False
        run.applied_at = now
        run.applied_by_id = actor.id
        run.error = None

        summary.dry_run = False
        summary.run_id = run.id
        summary.source_id = source.id
        run.summary = _serialize_summary(summary)

        previous_state = {
            "last_hash": source.last_hash,
            "last_prepared_hash": source.last_prepared_hash,
            "last_imported_at": source.last_imported_at.isoformat() if source.last_imported_at else None,
            "metadata": source.metadata_,
            "payload_snapshot": source.payload_snapshot,
        }

        source.last_hash = payload_hash
        source.last_prepared_hash = payload_hash
        source.last_imported_at = now
        source.metadata_ = context_source.get("metadata") or source.metadata_ or {}
        if context_source.get("payload_snapshot") is not None:
            source.payload_snapshot = context_source.get("payload_snapshot")
        source.options = context_source.get("options") or source.options or {}

        after_state = {
            "last_hash": source.last_hash,
            "last_prepared_hash": source.last_prepared_hash,
            "last_imported_at": source.last_imported_at.isoformat() if source.last_imported_at else None,
            "metadata": source.metadata_,
            "payload_snapshot": source.payload_snapshot,
        }

        state_context = run.context or {}
        state_context.setdefault("source_state", {})
        state_context["source_state"]["before"] = previous_state
        state_context["source_state"]["after"] = after_state
        state_context["source_state"]["archive_ids"] = [str(archive.id) for archive in archives]
        run.context = state_context

        approval = ImportApproval(
            run_id=run.id,
            approver_id=actor.id,
            decision=ImportApprovalDecision.APPROVED,
            comment=comment,
        )
        db.add(approval)

        db.add(run)
        db.add(source)
        db.commit()
    except Exception as exc:  # pragma: no cover - defensive
        db.rollback()
        logger.exception(
            "import_run_apply_failed",
            run_id=str(run.id),
            project_id=str(run.project_id),
        )
        run.status = ImportRunStatus.FAILED
        run.error = str(exc)
        db.add(run)
        db.commit()
        raise

    logger.info(
        "import_run_applied",
        run_id=str(run.id),
        project_id=str(run.project_id),
        actor_id=str(actor.id),
    )
    return summary


def rollback_import_run(
    db: Session,
    run: ImportRun,
    actor: User,
    *,
    comment: str | None = None,
) -> ImportSummary:
    if run.status != ImportRunStatus.APPLIED:
        raise http_exception(
            status_code=400,
            code=ErrorCode.BAD_REQUEST,
            message="Only applied runs can be rolled back",
        )

    summary = ImportSummary.model_validate(run.summary or {}) if run.summary else ImportSummary()
    source = run.source

    try:
        _restore_archives(db, run, actor, comment)

        run.status = ImportRunStatus.ROLLED_BACK
        run.rolled_back_at = datetime.now(timezone.utc)
        run.rolled_back_by_id = actor.id

        summary.details = summary.details or []
        summary.details.append("rolled_back=True")
        run.summary = _serialize_summary(summary)

        state_context = run.context or {}
        source_state = state_context.get("source_state", {})
        previous_state = source_state.get("before")
        if source is not None and previous_state is not None:
            source.last_hash = previous_state.get("last_hash")
            source.last_prepared_hash = previous_state.get("last_prepared_hash")
            previous_imported_at = previous_state.get("last_imported_at")
            source.last_imported_at = (
                datetime.fromisoformat(previous_imported_at)
                if isinstance(previous_imported_at, str)
                else None
            )
            source.metadata_ = previous_state.get("metadata") or {}
            source.payload_snapshot = previous_state.get("payload_snapshot")
            db.add(source)

        db.add(run)
        db.commit()
    except Exception as exc:  # pragma: no cover - defensive
        db.rollback()
        logger.exception(
            "import_run_rollback_failed",
            run_id=str(run.id),
            project_id=str(run.project_id),
        )
        run.error = str(exc)
        db.add(run)
        db.commit()
        raise

    logger.info(
        "import_run_rolled_back",
        run_id=str(run.id),
        project_id=str(run.project_id),
        actor_id=str(actor.id),
    )
    return summary


def _ensure_source(
    db: Session,
    project: Project,
    importer: ImporterKind,
    descriptor: SourceDescriptor,
) -> ImportSource:
    if descriptor.existing is not None:
        source = descriptor.existing
    else:
        stmt = select(ImportSource).where(
            ImportSource.project_id == project.id,
            ImportSource.importer == importer,
            ImportSource.is_deleted.is_(False),
        )
        if descriptor.location is None:
            stmt = stmt.where(ImportSource.location.is_(None))
        else:
            stmt = stmt.where(ImportSource.location == descriptor.location)
        source = db.execute(stmt).scalar_one_or_none()

    if source is None:
        source = ImportSource(
            project_id=project.id,
            importer=importer,
            source_type=descriptor.source_type,
            location=descriptor.location,
            options=descriptor.options or {},
            metadata_=descriptor.metadata or {},
        )
    else:
        source.source_type = descriptor.source_type
        source.location = descriptor.location
        source.options = descriptor.options or {}
        source.metadata_ = descriptor.metadata or {}

    db.add(source)
    db.flush()
    return source


def _build_diff(
    db: Session,
    project: Project,
    importer: ImporterKind,
    candidates: Iterable[ImportCandidate],
    source: ImportSource | None,
) -> tuple[ImportSummary, list[ImportChange]]:
    summary = ImportSummary(dry_run=True, source_id=source.id if source else None)
    changes: list[ImportChange] = []
    existing_map = _load_existing_map(db, project)
    processed_keys: set[tuple[str, str, str]] = set()

    for candidate in candidates:
        candidate.method = candidate.method.upper()
        compute_fingerprint(candidate)
        key = (candidate.method, candidate.normalized_path, candidate.version)

        if key in processed_keys:
            summary.skipped += 1
            changes.append(
                ImportChange(
                    change_type=ImportChangeType.SKIPPED,
                    method=candidate.method,
                    path=candidate.path,
                    normalized_path=candidate.normalized_path,
                    version=candidate.version,
                    name=candidate.name,
                    summary="Duplicate entry in import payload",
                    metadata=candidate.metadata,
                )
            )
            continue

        processed_keys.add(key)
        existing = existing_map.get(key)

        if existing is None:
            payload = candidate.as_payload()
            summary.created += 1
            changes.append(
                ImportChange(
                    change_type=ImportChangeType.CREATED,
                    method=candidate.method,
                    path=candidate.path,
                    normalized_path=candidate.normalized_path,
                    version=candidate.version,
                    name=candidate.name,
                    summary="Created new API",
                    diff={"payload": payload},
                    metadata=candidate.metadata,
                )
            )
            continue

        diff = _calculate_diff(existing, candidate)
        if diff:
            summary.updated += 1
            changes.append(
                ImportChange(
                    change_type=ImportChangeType.UPDATED,
                    method=candidate.method,
                    path=candidate.path,
                    normalized_path=candidate.normalized_path,
                    version=candidate.version,
                    name=candidate.name,
                    api_id=existing.id,
                    summary="Detected changes",
                    diff=diff,
                    metadata=candidate.metadata,
                )
            )
        else:
            summary.skipped += 1
            changes.append(
                ImportChange(
                    change_type=ImportChangeType.SKIPPED,
                    method=candidate.method,
                    path=candidate.path,
                    normalized_path=candidate.normalized_path,
                    version=candidate.version,
                    name=candidate.name,
                    api_id=existing.id,
                    summary="No changes detected",
                    metadata=candidate.metadata,
                )
            )

    if source is not None:
        for key, api in existing_map.items():
            if key in processed_keys:
                continue
            if api.import_source_id != source.id:
                continue
            summary.removed += 1
            changes.append(
                ImportChange(
                    change_type=ImportChangeType.REMOVED,
                    method=api.method,
                    path=api.path,
                    normalized_path=api.normalized_path,
                    version=api.version,
                    name=api.name,
                    api_id=api.id,
                    summary="Marked as deleted (missing from import)",
                    diff={"is_deleted": {"from": api.is_deleted, "to": True}},
                    metadata=api.metadata_ or {},
                )
            )

    summary.items = changes
    summary.details = _build_details(summary)
    return summary, changes


def _load_existing_map(db: Session, project: Project) -> dict[tuple[str, str, str], Api]:
    stmt = select(Api).where(
        Api.project_id == project.id,
        Api.is_deleted.is_(False),
    )
    records = db.execute(stmt).scalars().all()
    return {(api.method, api.normalized_path, api.version): api for api in records}


def _calculate_diff(existing: Api, candidate: ImportCandidate) -> dict[str, Any]:
    diff: dict[str, Any] = {}
    for field in significant_fields():
        if field == "metadata":
            existing_value = existing.metadata_ or {}
        else:
            existing_value = getattr(existing, field)
        candidate_value = getattr(candidate, field)
        if existing_value != candidate_value:
            diff[field] = {"from": existing_value, "to": candidate_value}
    if existing.source_key != candidate.source_key:
        diff["source_key"] = {"from": existing.source_key, "to": candidate.source_key}
    if existing.fingerprint != candidate.fingerprint:
        diff["fingerprint"] = {"from": existing.fingerprint, "to": candidate.fingerprint}
    return diff


def _build_details(summary: ImportSummary) -> list[str]:
    lines: list[str] = []
    if summary.created:
        lines.append(f"created={summary.created}")
    if summary.updated:
        lines.append(f"updated={summary.updated}")
    if summary.skipped:
        lines.append(f"skipped={summary.skipped}")
    if summary.removed:
        lines.append(f"removed={summary.removed}")
    return lines


def _serialize_summary(summary: ImportSummary) -> dict[str, Any]:
    return summary.model_dump(mode="json")


def _apply_changes(
    db: Session,
    run: ImportRun,
    source: ImportSource,
    changes: Iterable[ImportChange],
    actor: User,
) -> list[ApiArchive]:
    archives: list[ApiArchive] = []
    project_id = run.project_id

    for change in changes:
        if change.change_type == ImportChangeType.CREATED:
            payload = change.diff.get("payload") if isinstance(change.diff, dict) else None
            if not isinstance(payload, dict):
                raise http_exception(
                    status_code=400,
                    code=ErrorCode.BAD_REQUEST,
                    message="Created change is missing payload details",
                )
            archive = _apply_created_change(db, project_id, source, run, change, payload, actor)
            archives.append(archive)
        elif change.change_type == ImportChangeType.UPDATED:
            archive = _apply_updated_change(db, source, run, change, actor)
            if archive is not None:
                archives.append(archive)
        elif change.change_type == ImportChangeType.REMOVED:
            archive = _apply_removed_change(db, source, run, change, actor)
            if archive is not None:
                archives.append(archive)
        else:
            continue
    return archives


def _apply_created_change(
    db: Session,
    project_id: uuid.UUID,
    source: ImportSource,
    run: ImportRun,
    change: ImportChange,
    payload: dict[str, Any],
    actor: User,
) -> ApiArchive:
    fingerprint = payload.get("fingerprint")
    if not fingerprint:
        fingerprint = _compute_fingerprint_from_payload(payload)
    api = Api(
        project_id=project_id,
        name=payload.get("name") or change.name,
        method=change.method,
        path=payload.get("path") or change.path,
        normalized_path=change.normalized_path,
        version=change.version,
        group_name=payload.get("group_name"),
        headers=payload.get("headers") or {},
        params=payload.get("params") or {},
        body=payload.get("body") or {},
        mock_example=payload.get("mock_example") or {},
        metadata_=payload.get("metadata") or {},
        fingerprint=fingerprint,
        source_key=payload.get("source_key"),
        import_source_id=source.id,
        revision=1,
        previous_revision_id=None,
    )
    db.add(api)
    db.flush()

    archive = ApiArchive(
        project_id=project_id,
        api_id=api.id,
        run_id=run.id,
        change_type=ApiArchiveChangeType.CREATED,
        revision=api.revision,
        payload=_serialize_api(api),
        metadata_={"change": change.model_dump(mode="json")},
        applied_by_id=actor.id,
    )
    db.add(archive)
    db.flush()

    api.previous_revision_id = archive.id
    db.add(api)

    return archive


def _apply_updated_change(
    db: Session,
    source: ImportSource,
    run: ImportRun,
    change: ImportChange,
    actor: User,
) -> ApiArchive | None:
    api = _resolve_api_for_change(db, run.project_id, change)
    if api is None:
        logger.warning(
            "import_run_update_missing_api",
            run_id=str(run.id),
            api_id=str(change.api_id) if change.api_id else None,
            method=change.method,
            path=change.normalized_path,
        )
        return None

    snapshot = _serialize_api(api)
    archive = ApiArchive(
        project_id=run.project_id,
        api_id=api.id,
        run_id=run.id,
        change_type=ApiArchiveChangeType.UPDATED,
        revision=api.revision,
        payload=snapshot,
        metadata_={"change": change.model_dump(mode="json")},
        applied_by_id=actor.id,
    )
    db.add(archive)
    db.flush()

    for field, delta in change.diff.items():
        if not isinstance(delta, dict) or "to" not in delta:
            continue
        if field == "metadata":
            api.metadata_ = delta["to"] or {}
            continue
        if not hasattr(api, field):
            continue
        setattr(api, field, delta["to"])

    api.fingerprint = _compute_fingerprint_from_api(api)
    api.import_source_id = source.id
    api.previous_revision_id = archive.id
    api.revision = (api.revision or 0) + 1
    db.add(api)
    return archive


def _apply_removed_change(
    db: Session,
    source: ImportSource,
    run: ImportRun,
    change: ImportChange,
    actor: User,
) -> ApiArchive | None:
    api = _resolve_api_for_change(db, run.project_id, change)
    if api is None:
        logger.warning(
            "import_run_remove_missing_api",
            run_id=str(run.id),
            api_id=str(change.api_id) if change.api_id else None,
            method=change.method,
            path=change.normalized_path,
        )
        return None

    snapshot = _serialize_api(api)
    archive = ApiArchive(
        project_id=run.project_id,
        api_id=api.id,
        run_id=run.id,
        change_type=ApiArchiveChangeType.REMOVED,
        revision=api.revision,
        payload=snapshot,
        metadata_={"change": change.model_dump(mode="json")},
        applied_by_id=actor.id,
    )
    db.add(archive)
    db.flush()

    api.is_deleted = True
    api.import_source_id = source.id
    api.previous_revision_id = archive.id
    api.revision = (api.revision or 0) + 1
    db.add(api)
    return archive


def _restore_archives(
    db: Session,
    run: ImportRun,
    actor: User,
    comment: str | None = None,
) -> None:
    stmt = (
        select(ApiArchive)
        .where(ApiArchive.run_id == run.id, ApiArchive.is_deleted.is_(False))
        .order_by(ApiArchive.created_at.desc())
    )
    archives = db.execute(stmt).scalars().all()

    for archive in archives:
        if archive.change_type == ApiArchiveChangeType.CREATED:
            if archive.api is None:
                continue
            archive.api.is_deleted = True
            archive.api.previous_revision_id = archive.id
            archive.api.revision = (archive.api.revision or 0) + 1
            db.add(archive.api)
        else:
            api = archive.api
            if api is None:
                continue
            payload = archive.payload or {}
            api.name = payload.get("name", api.name)
            api.method = payload.get("method", api.method)
            api.path = payload.get("path", api.path)
            api.normalized_path = payload.get("normalized_path", api.normalized_path)
            api.version = payload.get("version", api.version)
            api.group_name = payload.get("group_name")
            api.headers = payload.get("headers") or {}
            api.params = payload.get("params") or {}
            api.body = payload.get("body") or {}
            api.mock_example = payload.get("mock_example") or {}
            api.metadata_ = payload.get("metadata") or {}
            api.fingerprint = payload.get("fingerprint")
            api.source_key = payload.get("source_key")
            api.import_source_id = payload.get("import_source_id")
            api.is_deleted = payload.get("is_deleted", False)
            api.previous_revision_id = archive.id
            api.revision = payload.get("revision", api.revision)
            db.add(api)

    approval = ImportApproval(
        run_id=run.id,
        approver_id=actor.id,
        decision=ImportApprovalDecision.REJECTED,
        comment=comment or "Rollback executed",
    )
    db.add(approval)


def _resolve_api_for_change(db: Session, project_id: uuid.UUID, change: ImportChange) -> Api | None:
    if change.api_id:
        api = db.get(Api, change.api_id)
        if api is not None:
            return api
    stmt = select(Api).where(
        Api.project_id == project_id,
        Api.method == change.method,
        Api.normalized_path == change.normalized_path,
        Api.version == change.version,
        Api.is_deleted.is_(False),
    )
    return db.execute(stmt).scalar_one_or_none()


def _serialize_api(api: Api) -> dict[str, Any]:
    return {
        "id": str(api.id),
        "project_id": str(api.project_id),
        "name": api.name,
        "method": api.method,
        "path": api.path,
        "normalized_path": api.normalized_path,
        "version": api.version,
        "group_name": api.group_name,
        "headers": api.headers,
        "params": api.params,
        "body": api.body,
        "mock_example": api.mock_example,
        "metadata": api.metadata_,
        "fingerprint": api.fingerprint,
        "source_key": api.source_key,
        "import_source_id": str(api.import_source_id) if api.import_source_id else None,
        "revision": api.revision,
        "previous_revision_id": str(api.previous_revision_id) if api.previous_revision_id else None,
        "is_deleted": api.is_deleted,
    }


def _compute_fingerprint_from_payload(payload: dict[str, Any]) -> str:
    data = {
        "name": payload.get("name"),
        "group_name": payload.get("group_name"),
        "path": payload.get("path"),
        "headers": payload.get("headers") or {},
        "params": payload.get("params") or {},
        "body": payload.get("body") or {},
        "mock_example": payload.get("mock_example") or {},
        "metadata": payload.get("metadata") or {},
    }
    return compute_hash(data)


def _compute_fingerprint_from_api(api: Api) -> str:
    data = {
        "name": api.name,
        "group_name": api.group_name,
        "path": api.path,
        "headers": api.headers or {},
        "params": api.params or {},
        "body": api.body or {},
        "mock_example": api.mock_example or {},
        "metadata": api.metadata_ or {},
    }
    return compute_hash(data)


__all__ = [
    "SourceDescriptor",
    "approve_import_run",
    "prepare_import_run",
    "rollback_import_run",
]
