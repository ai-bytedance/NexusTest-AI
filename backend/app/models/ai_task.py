from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:
    from app.models.project import Project


class TaskType(str, enum.Enum):
    GENERATE_CASES = "generate_cases"
    GENERATE_ASSERTIONS = "generate_assertions"
    GENERATE_MOCK = "generate_mock"
    SUMMARIZE_REPORT = "summarize_report"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class AITask(BaseModel, Base):
    __tablename__ = "ai_tasks"

    __table_args__ = (
        Index("ix_ai_tasks_input_payload_gin", "input_payload", postgresql_using="gin"),
        Index("ix_ai_tasks_output_payload_gin", "output_payload", postgresql_using="gin"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        "project_id",
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_type: Mapped[TaskType] = mapped_column(
        Enum(TaskType, name="ai_task_type_enum", native_enum=True),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="ai_task_status_enum", native_enum=True),
        nullable=False,
        default=TaskStatus.PENDING,
        server_default=text("'pending'::ai_task_status_enum"),
    )
    input_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    output_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="ai_tasks")
