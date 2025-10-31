from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum as SqlEnum, ForeignKey, Integer, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:
    from app.models.api import Api
    from app.models.import_source import ImportRun
    from app.models.project import Project
    from app.models.user import User

class ApiArchiveChangeType(str, enum.Enum):
    CREATED = "created"
    UPDATED = "updated"
    REMOVED = "removed"

class ApiArchive(BaseModel, Base):
    __tablename__ = "api_archives"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("apis.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("import_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    change_type: Mapped[ApiArchiveChangeType] = mapped_column(
        SqlEnum(ApiArchiveChangeType, name="api_archive_change_type", native_enum=False, validate_strings=True),
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    applied_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    project: Mapped[Project] = relationship("Project")
    api: Mapped[Api | None] = relationship("Api", back_populates="archives")
    run: Mapped[ImportRun] = relationship("ImportRun", back_populates="archives")
    applied_by: Mapped[User | None] = relationship("User")

__all__ = ["ApiArchive", "ApiArchiveChangeType"]
