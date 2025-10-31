from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:
    from app.models.agent import AgentQueueMembership
    from app.models.environment import Environment
    from app.models.execution_policy import ExecutionPolicy
    from app.models.project import Project
    from app.models.test_case import TestCase
    from app.models.test_report import TestReport
    from app.models.test_suite import TestSuite


class ExecutionQueueKind(str, enum.Enum):
    CASE = "case"
    SUITE = "suite"


class ExecutionQueue(BaseModel, Base):
    __tablename__ = "execution_queues"

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_execution_queues_project_name"),
        Index("ix_execution_queues_project_kind", "project_id", "kind"),
        Index("ix_execution_queues_routing_key", "routing_key", unique=True),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        "project_id",
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    environment_id: Mapped[uuid.UUID | None] = mapped_column(
        "environment_id",
        ForeignKey("environments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    routing_key: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[ExecutionQueueKind] = mapped_column(
        Enum(ExecutionQueueKind, name="execution_queue_kind_enum", native_enum=True),
        nullable=False,
        default=ExecutionQueueKind.CASE,
        server_default=text("'case'::execution_queue_kind_enum"),
    )
    concurrency_limit: Mapped[int | None] = mapped_column(nullable=True)
    rate_limit_qps: Mapped[float | None] = mapped_column(Float, nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("TRUE"),
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("FALSE"),
    )
    labels: Mapped[dict[str, list[str]]] = mapped_column(  # type: ignore[assignment]
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    project: Mapped["Project"] = relationship("Project", back_populates="queues")
    environment: Mapped[Optional["Environment"]] = relationship("Environment", back_populates="queues")
    test_cases: Mapped[list["TestCase"]] = relationship("TestCase", back_populates="queue")
    test_suites: Mapped[list["TestSuite"]] = relationship("TestSuite", back_populates="queue")
    reports: Mapped[list["TestReport"]] = relationship("TestReport", back_populates="queue")
    policies: Mapped[list["ExecutionPolicy"]] = relationship("ExecutionPolicy", back_populates="queue")
    agent_memberships: Mapped[list["AgentQueueMembership"]] = relationship(
        "AgentQueueMembership",
        back_populates="queue",
        cascade="all, delete-orphan",
    )


__all__ = [
    "ExecutionQueue",
    "ExecutionQueueKind",
]
