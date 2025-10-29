from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:
    from app.models.api import Api
    from app.models.project import Project


class ImporterKind(str, enum.Enum):
    OPENAPI = "openapi"
    POSTMAN = "postman"


class ImportSourceType(str, enum.Enum):
    URL = "url"
    FILE = "file"
    RAW = "raw"


class ImportRunStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


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
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
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
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
        default=ImportRunStatus.COMPLETED,
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
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="import_runs")
    source: Mapped[ImportSource | None] = relationship("ImportSource", back_populates="runs")
