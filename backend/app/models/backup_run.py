from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Float, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BaseModel


class BackupStatus(str, enum.Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class BackupRun(BaseModel, Base):
    __tablename__ = "backup_runs"

    __table_args__ = (Index("ix_backup_runs_started_at", "started_at"),)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("TIMEZONE('utc', NOW())"),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[BackupStatus] = mapped_column(
        Enum(BackupStatus, name="backup_status_enum", native_enum=True),
        nullable=False,
        default=BackupStatus.RUNNING,
        server_default=text("'running'::backup_status_enum"),
    )
    storage_targets: Mapped[str] = mapped_column(String(64), nullable=False, default="local", server_default=text("'local'"))
    location: Mapped[str] = mapped_column(String(1024), nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    retention_class: Mapped[str] = mapped_column(String(32), nullable=False, default="daily", server_default=text("'daily'"))
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )
    triggered_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verify_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = ["BackupRun", "BackupStatus"]
