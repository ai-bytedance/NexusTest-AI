from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.api import Api
from app.models.import_source import (
    ImportRun,
    ImportRunStatus,
    ImportSource,
    ImportSourceType,
    ImporterKind,
)
from app.schemas.importers import ImportChange, ImportChangeType, ImportSummary
from app.services.importers.common import ImportCandidate, compute_fingerprint, significant_fields


@dataclass(slots=True)
class SourceDescriptor:
    source_type: ImportSourceType
    location: str | None
    content_hash: str
    options: dict[str, Any]
    payload_snapshot: dict[str, Any] | None
    metadata: dict[str, Any]
    existing: ImportSource | None = None


class ImportManager:
    def __init__(
        self,
        db: Session,
        project,
        importer: ImporterKind,
        *,
        dry_run: bool = False,
    ) -> None:
        self.db = db
        self.project = project
        self.importer = importer
        self.dry_run = dry_run

    def run(self, candidates: Iterable[ImportCandidate], descriptor: SourceDescriptor) -> ImportSummary:
        source = self._ensure_source(descriptor)
        summary = ImportSummary(dry_run=self.dry_run, source_id=source.id if source else None)
        changes: list[ImportChange] = []

        existing_map = self._load_existing()
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
                        diff={"payload": candidate.as_payload()},
                        metadata=candidate.metadata,
                    )
                )
                if not self.dry_run:
                    self._create_api(candidate, source)
                continue

            diff = self._calculate_diff(existing, candidate)
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
                        summary="Detected changes",
                        diff=diff,
                        metadata=candidate.metadata,
                    )
                )
                if not self.dry_run:
                    self._update_api(existing, candidate, source)
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
                        summary="No changes detected",
                        metadata=candidate.metadata,
                    )
                )
                if not self.dry_run and existing.import_source_id != (source.id if source else None):
                    existing.import_source_id = source.id if source else None
                    self.db.add(existing)

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
                        summary="Marked as deleted (missing from import)",
                        diff={"is_deleted": {"from": api.is_deleted, "to": True}},
                        metadata=api.metadata_ or {},
                    )
                )
                if not self.dry_run:
                    api.is_deleted = True
                    self.db.add(api)

        summary.items = changes
        summary.details = self._build_details(summary)

        run = ImportRun(
            project_id=self.project.id,
            source_id=source.id if source else None,
            importer=self.importer,
            dry_run=self.dry_run,
            status=ImportRunStatus.COMPLETED,
            summary=self._serialize_summary(summary),
            diff=[change.model_dump() for change in changes],
        )
        self.db.add(run)
        self.db.flush()

        summary.run_id = run.id
        if source is not None:
            summary.source_id = source.id

        if source is not None and not self.dry_run:
            source.last_run_at = datetime.now(timezone.utc)
            self.db.add(source)

        self.db.commit()
        return summary

    def _ensure_source(self, descriptor: SourceDescriptor) -> ImportSource | None:
        options = descriptor.options or {}
        metadata = descriptor.metadata or {}
        payload_snapshot = descriptor.payload_snapshot
        target: ImportSource | None = descriptor.existing

        if target is None:
            target = self._find_existing_source(descriptor.source_type, descriptor.location)

        if target is None:
            target = ImportSource(
                project_id=self.project.id,
                importer=self.importer,
                source_type=descriptor.source_type,
                location=descriptor.location,
                content_hash=descriptor.content_hash,
                options=options,
                payload_snapshot=payload_snapshot,
                metadata_=metadata,
            )
        else:
            target.content_hash = descriptor.content_hash
            target.options = options
            target.payload_snapshot = payload_snapshot
            target.metadata_ = metadata

        self.db.add(target)
        self.db.flush()
        return target

    def _find_existing_source(self, source_type: ImportSourceType, location: str | None) -> ImportSource | None:
        stmt = select(ImportSource).where(
            ImportSource.project_id == self.project.id,
            ImportSource.importer == self.importer,
            ImportSource.source_type == source_type,
        )
        if location is None:
            stmt = stmt.where(ImportSource.location.is_(None))
        else:
            stmt = stmt.where(ImportSource.location == location)
        return self.db.execute(stmt).scalar_one_or_none()

    def _load_existing(self) -> dict[tuple[str, str, str], Api]:
        stmt = select(Api).where(
            Api.project_id == self.project.id,
            Api.is_deleted.is_(False),
        )
        records = self.db.execute(stmt).scalars().all()
        return {(api.method, api.normalized_path, api.version): api for api in records}

    def _calculate_diff(self, existing: Api, candidate: ImportCandidate) -> dict[str, Any]:
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
        return diff

    def _create_api(self, candidate: ImportCandidate, source: ImportSource | None) -> None:
        payload = candidate.as_payload()
        api = Api(
            project_id=self.project.id,
            name=payload["name"],
            method=candidate.method,
            path=payload["path"],
            normalized_path=payload["normalized_path"],
            version=payload["version"],
            group_name=payload["group_name"],
            headers=payload["headers"],
            params=payload["params"],
            body=payload["body"],
            mock_example=payload["mock_example"],
            metadata_=payload["metadata"],
            fingerprint=candidate.fingerprint,
            source_key=candidate.source_key,
            import_source_id=source.id if source else None,
        )
        self.db.add(api)

    def _update_api(self, api: Api, candidate: ImportCandidate, source: ImportSource | None) -> None:
        payload = candidate.as_payload()
        api.name = payload["name"]
        api.path = payload["path"]
        api.normalized_path = payload["normalized_path"]
        api.version = payload["version"]
        api.group_name = payload["group_name"]
        api.headers = payload["headers"]
        api.params = payload["params"]
        api.body = payload["body"]
        api.mock_example = payload["mock_example"]
        api.metadata_ = payload["metadata"]
        api.source_key = payload["source_key"]
        api.fingerprint = candidate.fingerprint
        api.import_source_id = source.id if source else None
        self.db.add(api)

    def _build_details(self, summary: ImportSummary) -> list[str]:
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

    def _serialize_summary(self, summary: ImportSummary) -> dict[str, Any]:
        return {
            "created": summary.created,
            "updated": summary.updated,
            "skipped": summary.skipped,
            "removed": summary.removed,
            "dry_run": summary.dry_run,
            "details": summary.details,
            "source_id": str(summary.source_id) if summary.source_id else None,
        }
