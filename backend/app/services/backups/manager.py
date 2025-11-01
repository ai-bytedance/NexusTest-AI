from __future__ import annotations

import hashlib
import os
import shlex
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy import Select, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.logging import get_logger
from app.models.backup_run import BackupRun, BackupStatus
from app.observability.metrics import record_backup_result

logger = get_logger()


@dataclass(frozen=True)
class BackupPlan:
    timestamp: datetime
    directory: Path
    filename: str

    @property
    def path(self) -> Path:
        return self.directory / self.filename


class BackupManager:
    def __init__(self, session: Session, settings: Optional[Settings] = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self._base_dir = Path(self.settings.backup_base_dir).expanduser().resolve()

    @classmethod
    def create(cls, session: Session) -> "BackupManager":
        return cls(session=session, settings=get_settings())

    def plan_backup(self, *, timestamp: Optional[datetime] = None) -> BackupPlan:
        ts = timestamp or datetime.now(timezone.utc)
        day_dir = self._base_dir / f"{ts.year:04d}" / f"{ts.month:02d}" / f"{ts.day:02d}"
        filename = f"backup-{ts.strftime('%Y%m%dT%H%M%SZ')}.dump"
        return BackupPlan(timestamp=ts, directory=day_dir, filename=filename)

    def run_backup(self, *, triggered_by: str | None = None) -> BackupRun:
        plan = self.plan_backup()
        plan.directory.mkdir(parents=True, exist_ok=True)

        backup_run = BackupRun(
            started_at=plan.timestamp,
            location=str(plan.path),
            storage_targets="local",
            triggered_by=triggered_by,
            retention_class="daily",
            metadata_={"local_path": str(plan.path)},
        )
        self.session.add(backup_run)
        self.session.commit()
        logger.info("backup_started", backup_id=str(backup_run.id), path=str(plan.path))

        duration: float | None = None
        failure_reason: str | None = None
        final_path = plan.path
        metadata = backup_run.metadata_ or {}

        try:
            start_time = time.perf_counter()
            dump_path = self._execute_pg_dump(plan)
            final_path = dump_path

            if self.settings.backup_encrypt:
                maybe_encrypted = self._maybe_encrypt(dump_path)
                if maybe_encrypted is not None:
                    final_path = maybe_encrypted
                    metadata["encrypted"] = True
                else:
                    metadata["encrypted"] = False

            size_bytes = final_path.stat().st_size if final_path.exists() else None
            checksum = self._compute_checksum(final_path)

            storage_targets = {"local"}
            metadata["checksum_sha256"] = checksum
            metadata["size_bytes"] = size_bytes
            metadata["created_at"] = plan.timestamp.isoformat()

            remote_uri = self._maybe_upload_to_s3(final_path)
            if remote_uri:
                storage_targets.add("s3")
                metadata["s3_uri"] = remote_uri

            verify_notes: str | None = None
            if self._should_verify_restore(plan.timestamp):
                verify_notes = self._attempt_restore_verification(final_path)
                if verify_notes:
                    metadata["verify_notes"] = verify_notes
                    backup_run.verify_notes = verify_notes
                backup_run.verified_at = datetime.now(timezone.utc)

            duration = time.perf_counter() - start_time

            backup_run.finished_at = datetime.now(timezone.utc)
            backup_run.status = BackupStatus.SUCCESS
            backup_run.duration_seconds = duration
            backup_run.size_bytes = size_bytes
            backup_run.checksum = checksum
            backup_run.storage_targets = ",".join(sorted(storage_targets))
            backup_run.location = str(final_path)
            backup_run.metadata_ = metadata

            self.session.add(backup_run)
            self.session.commit()

            self._enforce_retention()

            record_backup_result(
                storages=backup_run.storage_targets.split(","),
                status=backup_run.status.value,
                duration_seconds=duration,
                size_bytes=size_bytes,
                finished_at=backup_run.finished_at,
            )

            logger.info(
                "backup_completed",
                backup_id=str(backup_run.id),
                duration_seconds=round(duration or 0.0, 2),
                size_bytes=size_bytes,
                storages=list(storage_targets),
            )

            return backup_run
        except Exception as exc:  # noqa: BLE001
            failure_reason = exc.__class__.__name__
            backup_run.status = BackupStatus.FAILED
            backup_run.error_message = str(exc)
            backup_run.finished_at = datetime.now(timezone.utc)
            self.session.add(backup_run)
            self.session.commit()

            record_backup_result(
                storages=(backup_run.storage_targets.split(",") if backup_run.storage_targets else ("local",)),
                status=backup_run.status.value,
                duration_seconds=duration,
                size_bytes=backup_run.size_bytes,
                finished_at=backup_run.finished_at,
                failure_reason=failure_reason,
            )

            logger.exception("backup_failed", backup_id=str(backup_run.id))
            raise

    # Internal helpers -----------------------------------------------------

    def _execute_pg_dump(self, plan: BackupPlan) -> Path:
        url = self._resolve_database_url()
        self._assert_postgres(url)

        output_path = plan.path
        env = os.environ.copy()
        if url.password:
            env["PGPASSWORD"] = url.password

        command = [
            "pg_dump",
            "--format=custom",
            "--compress=9",
            "--no-owner",
            "--no-privileges",
            "--file",
            str(output_path),
            "--host",
            url.host or "localhost",
            "--port",
            str(url.port or 5432),
            "--username",
            url.username or "postgres",
            url.database or "postgres",
        ]

        self._run_subprocess(command, env=env)
        if "PGPASSWORD" in env:
            env.pop("PGPASSWORD", None)
        return output_path

    def _maybe_encrypt(self, dump_path: Path) -> Path | None:
        if not self.settings.backup_encrypt:
            return None

        recipient = (self.settings.backup_gpg_recipient or "").strip()
        if not recipient:
            logger.warning("backup_encryption_recipient_missing")
            return None

        if shutil.which("gpg") is None:
            logger.warning("backup_encryption_gpg_missing")
            return None

        encrypted_path = dump_path.with_suffix(dump_path.suffix + ".gpg")
        env = os.environ.copy()
        if self.settings.backup_gpg_public_key_path:
            key_path = Path(self.settings.backup_gpg_public_key_path).expanduser()
            if key_path.exists():
                self._run_subprocess([
                    "gpg",
                    "--batch",
                    "--yes",
                    "--import",
                    str(key_path),
                ], env=env)

        command = [
            "gpg",
            "--batch",
            "--yes",
            "--trust-model",
            "always",
            "--recipient",
            recipient,
            "--output",
            str(encrypted_path),
            "--encrypt",
            str(dump_path),
        ]

        self._run_subprocess(command, env=env)
        dump_path.unlink(missing_ok=True)
        return encrypted_path

    def _maybe_upload_to_s3(self, file_path: Path) -> str | None:
        bucket = (self.settings.backup_s3_bucket or "").strip()
        if not bucket:
            return None

        try:
            import boto3  # type: ignore
        except ImportError:
            logger.warning("backup_s3_dependency_missing")
            return None

        prefix = self.settings.backup_s3_prefix
        key = f"{prefix}{file_path.name}" if prefix else file_path.name
        client_kwargs: dict[str, object] = {}
        if self.settings.backup_s3_region:
            client_kwargs["region_name"] = self.settings.backup_s3_region
        if self.settings.backup_s3_endpoint_url:
            client_kwargs["endpoint_url"] = self.settings.backup_s3_endpoint_url
        if self.settings.backup_s3_access_key and self.settings.backup_s3_secret_key:
            client_kwargs["aws_access_key_id"] = self.settings.backup_s3_access_key
            client_kwargs["aws_secret_access_key"] = self.settings.backup_s3_secret_key
        if not self.settings.backup_s3_use_ssl:
            client_kwargs["use_ssl"] = False

        client = boto3.client("s3", **client_kwargs)
        client.upload_file(str(file_path), bucket, key)
        uri = f"s3://{bucket}/{key}"
        logger.info("backup_uploaded", uri=uri)
        return uri

    def _should_verify_restore(self, reference: datetime) -> bool:
        interval_days = self.settings.backup_verify_every_n_days
        if interval_days <= 0:
            return False

        stmt: Select[BackupRun] = (
            select(BackupRun)
            .where(BackupRun.verified_at.is_not(None), BackupRun.is_deleted.is_(False))
            .order_by(BackupRun.verified_at.desc())
        )
        last_verified = self.session.execute(stmt).scalars().first()
        if not last_verified or not last_verified.verified_at:
            return True
        delta = reference - last_verified.verified_at
        return delta >= timedelta(days=interval_days)

    def _attempt_restore_verification(self, backup_path: Path) -> str | None:
        if backup_path.suffix.endswith(".gpg"):
            return "skipped_encrypted"

        url = self._resolve_database_url()
        env = os.environ.copy()
        if url.password:
            env["PGPASSWORD"] = url.password

        temp_db = f"backup_verify_{uuid.uuid4().hex[:8]}"
        host = url.host or "localhost"
        port = str(url.port or 5432)
        user = url.username or "postgres"

        create_cmd = [
            "psql",
            "--host",
            host,
            "--port",
            port,
            "--username",
            user,
            "--command",
            f'CREATE DATABASE "{temp_db}" TEMPLATE template0;',
        ]
        drop_cmd = [
            "psql",
            "--host",
            host,
            "--port",
            port,
            "--username",
            user,
            "--command",
            f'DROP DATABASE IF EXISTS "{temp_db}";',
        ]
        restore_cmd = [
            "pg_restore",
            "--clean",
            "--if-exists",
            "--exit-on-error",
            "--host",
            host,
            "--port",
            port,
            "--username",
            user,
            "--dbname",
            temp_db,
            str(backup_path),
        ]

        try:
            self._run_subprocess(create_cmd, env=env)
            self._run_subprocess(restore_cmd, env=env)
            return "verified"
        except Exception as exc:  # noqa: BLE001
            logger.warning("backup_verify_failed", reason=str(exc))
            return f"verify_failed:{exc.__class__.__name__}"
        finally:
            try:
                self._run_subprocess(drop_cmd, env=env)
            except Exception:  # noqa: BLE001
                logger.warning("backup_verify_cleanup_failed", database=temp_db)

    def _compute_checksum(self, path: Path) -> str | None:
        if not path.exists() or not path.is_file():
            return None
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _enforce_retention(self) -> None:
        backups: list[BackupRun] = (
            self.session.execute(
                select(BackupRun)
                .where(BackupRun.is_deleted.is_(False), BackupRun.status == BackupStatus.SUCCESS)
                .order_by(BackupRun.started_at.desc())
            )
            .scalars()
            .all()
        )
        if not backups:
            return

        now = datetime.now(timezone.utc)
        keep_ids: set[uuid.UUID] = set()
        retention_labels: dict[uuid.UUID, str] = {}

        self._select_daily_backups(backups, now, keep_ids, retention_labels)
        self._select_weekly_backups(backups, now, keep_ids, retention_labels)
        self._select_monthly_backups(backups, now, keep_ids, retention_labels)

        for backup in backups:
            if backup.id in keep_ids:
                backup.retention_class = retention_labels.get(backup.id, "daily")
                continue
            self._remove_backup_assets(backup)
            backup.is_deleted = True
            self.session.add(backup)

        self.session.commit()

    def _select_daily_backups(
        self,
        backups: Iterable[BackupRun],
        now: datetime,
        keep_ids: set[uuid.UUID],
        retention_labels: dict[uuid.UUID, str],
    ) -> None:
        days = self.settings.backup_keep_daily
        if days <= 0:
            return
        seen_days: set[datetime.date] = set()
        for backup in backups:
            day = backup.started_at.date()
            delta = (now.date() - day).days
            if delta < 0 or delta >= days:
                continue
            if day in seen_days:
                continue
            keep_ids.add(backup.id)
            retention_labels[backup.id] = "daily"
            seen_days.add(day)
            if len(seen_days) >= days:
                break

    def _select_weekly_backups(
        self,
        backups: Iterable[BackupRun],
        now: datetime,
        keep_ids: set[uuid.UUID],
        retention_labels: dict[uuid.UUID, str],
    ) -> None:
        weeks = self.settings.backup_keep_weekly
        if weeks <= 0:
            return
        seen_weeks: set[tuple[int, int]] = set()
        for backup in backups:
            if backup.id in keep_ids:
                continue
            iso_year, iso_week, _ = backup.started_at.isocalendar()
            week_key = (iso_year, iso_week)
            day_delta = (now.date() - backup.started_at.date()).days
            if day_delta < self.settings.backup_keep_daily:
                continue
            if week_key in seen_weeks:
                continue
            keep_ids.add(backup.id)
            retention_labels[backup.id] = "weekly"
            seen_weeks.add(week_key)
            if len(seen_weeks) >= weeks:
                break

    def _select_monthly_backups(
        self,
        backups: Iterable[BackupRun],
        now: datetime,
        keep_ids: set[uuid.UUID],
        retention_labels: dict[uuid.UUID, str],
    ) -> None:
        months = self.settings.backup_keep_monthly
        if months <= 0:
            return
        seen_months: set[tuple[int, int]] = set()
        for backup in backups:
            if backup.id in keep_ids:
                continue
            month_key = (backup.started_at.year, backup.started_at.month)
            day_delta = (now.date() - backup.started_at.date()).days
            weekly_span = self.settings.backup_keep_daily + (self.settings.backup_keep_weekly * 7)
            if day_delta < weekly_span:
                continue
            if month_key in seen_months:
                continue
            keep_ids.add(backup.id)
            retention_labels[backup.id] = "monthly"
            seen_months.add(month_key)
            if len(seen_months) >= months:
                break

    def _remove_backup_assets(self, backup: BackupRun) -> None:
        path = Path(backup.location)
        if path.exists():
            try:
                path.unlink()
                logger.info("backup_pruned", backup_id=str(backup.id), path=str(path))
            except Exception as exc:  # noqa: BLE001
                logger.warning("backup_prune_failed", backup_id=str(backup.id), reason=str(exc))
        metadata = backup.metadata or {}
        s3_uri = metadata.get("s3_uri") if isinstance(metadata, dict) else None
        if s3_uri:
            self._delete_s3_object(s3_uri)

    def _delete_s3_object(self, uri: str) -> None:
        if not uri.startswith("s3://"):
            return
        bucket_key = uri[5:]
        if "/" not in bucket_key:
            return
        bucket, key = bucket_key.split("/", 1)
        try:
            import boto3  # type: ignore
        except ImportError:
            logger.warning("backup_s3_dependency_missing_for_delete")
            return
        client = boto3.client("s3")
        client.delete_object(Bucket=bucket, Key=key)
        logger.info("backup_remote_deleted", uri=uri)

    def _resolve_database_url(self) -> URL:
        return make_url(self.settings.database_url)

    def _assert_postgres(self, url: URL) -> None:
        if url.drivername.split("+")[0] not in {"postgresql", "postgres"}:
            raise RuntimeError("Backups are supported only for PostgreSQL")

    def _run_subprocess(self, command: list[str], env: Optional[dict[str, str]] = None) -> None:
        display = shlex.join(command)
        logger.debug("backup_exec", command=display)
        try:
            subprocess.run(command, env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as exc:  # pragma: no cover - subprocess error path
            stderr = (exc.stderr.decode("utf-8", errors="ignore") if exc.stderr else "").strip()
            raise RuntimeError(f"Command failed: {display}: {stderr}") from exc


__all__ = ["BackupManager", "BackupPlan"]
