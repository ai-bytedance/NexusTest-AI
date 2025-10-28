from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:
    from app.models.project import Project


class ReportEntityType(str, enum.Enum):
    CASE = "case"
    SUITE = "suite"


class ReportStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


class TestReport(BaseModel, Base):
    __tablename__ = "test_reports"

    __table_args__ = (
        Index("ix_test_reports_entity", "entity_type", "entity_id"),
        Index("ix_test_reports_request_payload_gin", "request_payload", postgresql_using="gin"),
        Index("ix_test_reports_response_payload_gin", "response_payload", postgresql_using="gin"),
        Index("ix_test_reports_assertions_result_gin", "assertions_result", postgresql_using="gin"),
        Index("ix_test_reports_metrics_gin", "metrics", postgresql_using="gin"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        "project_id",
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[ReportEntityType] = mapped_column(
        Enum(ReportEntityType, name="report_entity_type_enum", native_enum=True),
        nullable=False,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        "entity_id",
        PGUUID(as_uuid=True),
        nullable=False,
    )
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, name="report_status_enum", native_enum=True),
        nullable=False,
        default=ReportStatus.PENDING,
        server_default=text("'pending'::report_status_enum"),
    )
    started_at: Mapped[datetime] = mapped_column(  # type: ignore[name-defined]
        DateTime(timezone=True),
        nullable=False,
        server_default=text("TIMEZONE('utc', NOW())"),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    request_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    response_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    assertions_result: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="test_reports")
