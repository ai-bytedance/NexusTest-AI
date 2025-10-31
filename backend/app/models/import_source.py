from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:
    from app.models.api import Api
    from app.models.api_archive import ApiArchive
    from app.models.project import Project
    from app.models.user import User


class ImporterKind(str, enum.Enum):
    OPENAPI = "openapi"
    POSTMAN = "postman"


class ImportSourceType(str, enum.Enum):
    URL = "url"
    FILE = "file"
    RAW = "raw"


class ImportRunStatus(str, enum.Enum):
    PENDING = "pending"
    DIFF_READY = "diff_ready"
    APPLIED = "applied"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class ImportApprovalDecision(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ImportSource(BaseModel, Base):
    __tablename__ = "import_sources"

    project_id: Mapped[uuid.UUID] = mapped_column(
        "project_id",
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    importer: Mapped[ImporterKind] = mapped_column(
        SqlEnum(ImporterKind, name="importer_kind", native_enum=False, validate_strings=True),
        nullable=False,
    )
    source_type: Mapped[ImportSourceType] = mapped_column(
        SqlEnum(ImportSourceType, name="import_source_type", native_enum=False, validate_strings=True),
        nullable=False,
    )
    location: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    options: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    payload_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    last_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    last_prepared_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    last_imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_prepared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_rules: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    project: Mapped["Project"] = relationship("Project", back_populates="import_sources")
    apis: Mapped[list["Api"]] = relationship("Api", back_populates="import_source")
    runs: Mapped[list["ImportRun"]] = relationship(
        "ImportRun",
        back_populates="source",
        cascade="all, delete-orphan",
    )


class ImportRun(BaseModel, Base):
    __tablename__ = "import_runs"

    project_id: Mapped[uuid.UUID] = mapped_column(
        "project_id",
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("import_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    importer: Mapped[ImporterKind] = mapped_column(
        SqlEnum(ImporterKind, name="importer_kind", native_enum=False, validate_strings=True),
        nullable=False,
    )
    dry_run: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default=text("FALSE"),
    )
    status: Mapped[ImportRunStatus] = mapped_column(
        SqlEnum(ImportRunStatus, name="import_run_status", native_enum=False, validate_strings=True),
        nullable=False,
        default=ImportRunStatus.PENDING,
        server_default=text("'pending'"),
    )
    summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    diff: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    context: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    applied_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rolled_back_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="import_runs")
    source: Mapped[ImportSource | None] = relationship("ImportSource", back_populates="runs")
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])
    applied_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[applied_by_id])
    rolled_back_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[rolled_back_by_id])
    approvals: Mapped[list["ImportApproval"]] = relationship(
        "ImportApproval",
        back_populates="run",
        cascade="all, delete-orphan",
    )
    archives: Mapped[list["ApiArchive"]] = relationship(
        "ApiArchive",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class ImportApproval(BaseModel, Base):
    __tablename__ = "import_approvals"

    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("import_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    approver_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    decision: Mapped[ImportApprovalDecision] = mapped_column(
        SqlEnum(ImportApprovalDecision, name="import_approval_decision", native_enum=False, validate_strings=True),
        nullable=False,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[ImportRun] = relationship("ImportRun", back_populates="approvals")
    approver: Mapped["User"] = relationship("User")


__all__ = [
    "ImportSource",
    "ImportSourceType",
    "ImportRun",
    "ImportRunStatus",
    "ImportApproval",
    "ImportApprovalDecision",
    "ImporterKind",
]
