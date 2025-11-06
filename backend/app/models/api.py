from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:
    from app.models.api_archive import ApiArchive
    from app.models.import_source import ImportSource
    from app.models.project import Project
    from app.models.test_case import TestCase

class Api(BaseModel, Base):
    __tablename__ = "apis"

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "method",
            "normalized_path",
            "version",
            name="uq_apis_project_method_normalized_path_version",
        ),
        Index("ix_apis_headers_gin", "headers", postgresql_using="gin"),
        Index("ix_apis_params_gin", "params", postgresql_using="gin"),
        Index("ix_apis_body_gin", "body", postgresql_using="gin"),
        Index("ix_apis_mock_example_gin", "mock_example", postgresql_using="gin"),
        Index("ix_apis_import_source_id", "import_source_id"),
        Index("ix_apis_fingerprint", "fingerprint"),
        Index("ix_apis_previous_revision_id", "previous_revision_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        "project_id",
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_path: Mapped[str] = mapped_column(String(512), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'v1'"))
    group_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    headers: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    body: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    mock_example: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    previous_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("api_archives.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    import_source_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("import_sources.id", ondelete="SET NULL"),
        nullable=True,
    )

    project: Mapped[Project] = relationship("Project", back_populates="apis")
    import_source: Mapped[ImportSource | None] = relationship("ImportSource", back_populates="apis")
    test_cases: Mapped[list[TestCase]] = relationship(
        "TestCase", back_populates="api", cascade="all, delete-orphan"
    )
    previous_revision: Mapped[ApiArchive | None] = relationship(
        "ApiArchive",
        foreign_keys=[previous_revision_id],
    )
    archives: Mapped[list[ApiArchive]] = relationship(
        "ApiArchive",
        back_populates="api",
        cascade="all, delete-orphan",
        foreign_keys="ApiArchive.api_id",
        primaryjoin="Api.id == ApiArchive.api_id",
    )
