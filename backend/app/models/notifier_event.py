from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:
    from app.models.notifier import Notifier
    from app.models.project import Project


class NotifierEventType(str, enum.Enum):
    RUN_FINISHED = "run_finished"
    IMPORT_DIFF_READY = "import_diff_ready"
    IMPORT_APPLIED = "import_applied"
    IMPORT_FAILED = "import_failed"
    ISSUE_CREATED = "issue_created"
    ISSUE_CLOSED = "issue_closed"


class NotifierEventStatus(str, enum.Enum):
    PENDING = "pending"
    DELIVERING = "delivering"
    RETRYING = "retrying"
    SUCCESS = "success"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class NotifierEvent(BaseModel, Base):
    __tablename__ = "notifier_events"

    __table_args__ = (
        Index("ix_notifier_events_project_id", "project_id"),
        Index("ix_notifier_events_status", "status"),
        Index("ix_notifier_events_created_at", "created_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    notifier_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notifiers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event: Mapped[NotifierEventType] = mapped_column(
        Enum(NotifierEventType, name="notifier_event_type_enum", native_enum=True),
        nullable=False,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[NotifierEventStatus] = mapped_column(
        Enum(NotifierEventStatus, name="notifier_event_status_enum", native_enum=True),
        nullable=False,
        default=NotifierEventStatus.PENDING,
        server_default=text("'pending'::notifier_event_status_enum"),
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    notifier: Mapped["Notifier"] = relationship("Notifier", back_populates="events")
    project: Mapped["Project"] = relationship("Project", back_populates="notifier_events")


__all__ = ["NotifierEvent", "NotifierEventStatus", "NotifierEventType"]
