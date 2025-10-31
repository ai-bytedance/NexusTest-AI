from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:
    from app.models.integration import Integration
    from app.models.project import Project
    from app.models.test_report import TestReport
    from app.models.user import User

class IssueLinkSource(str, enum.Enum):
    MANUAL = "manual"
    AUTO = "auto"

class IssueSyncState(str, enum.Enum):
    OK = "ok"
    ERROR = "error"

class Issue(BaseModel, Base):
    __tablename__ = "issues"

    __table_args__ = (
        Index("ix_issues_project_id", "project_id"),
        Index("ix_issues_provider", "provider"),
        Index("ix_issues_dedupe_key", "dedupe_key"),
        UniqueConstraint("provider", "external_id", name="uq_issues_provider_external"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    integration_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("integrations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="open")
    sync_state: Mapped[IssueSyncState] = mapped_column(
        Enum(IssueSyncState, name="issue_sync_state_enum", native_enum=True),
        nullable=False,
        default=IssueSyncState.OK,
        server_default=text("'ok'::issue_sync_state_enum"),
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_webhook_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    external_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    linked_prs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    linked_commits: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    project: Mapped[Project] = relationship("Project", back_populates="issues")
    integration: Mapped[Integration | None] = relationship("Integration", back_populates="issues")
    creator: Mapped[User | None] = relationship("User", back_populates="issues_created")
    links: Mapped[list[ReportIssueLink]] = relationship(
        "ReportIssueLink",
        back_populates="issue",
        cascade="all, delete-orphan",
    )

class ReportIssueLink(BaseModel, Base):
    __tablename__ = "report_issue_links"

    __table_args__ = (
        UniqueConstraint("report_id", "issue_id", name="uq_report_issue_link"),
        Index("ix_report_issue_links_report", "report_id"),
        Index("ix_report_issue_links_issue", "issue_id"),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"),
        nullable=False,
    )
    linked_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source: Mapped[IssueLinkSource] = mapped_column(
        Enum(IssueLinkSource, name="issue_link_source_enum", native_enum=True),
        nullable=False,
        default=IssueLinkSource.MANUAL,
        server_default=text("'manual'::issue_link_source_enum"),
    )
    note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    report: Mapped[TestReport] = relationship("TestReport", back_populates="issue_links")
    issue: Mapped[Issue] = relationship("Issue", back_populates="links")
    linker: Mapped[User | None] = relationship("User", back_populates="issue_links_created")

__all__ = ["Issue", "ReportIssueLink", "IssueLinkSource", "IssueSyncState"]
