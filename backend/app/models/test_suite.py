from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel
from app.models.execution_routing import AgentSelectionPolicy

if TYPE_CHECKING:
    from app.models.execution_queue import ExecutionQueue
    from app.models.project import Project
    from app.models.user import User


class TestSuite(BaseModel, Base):
    __tablename__ = "test_suites"

    __table_args__ = (
        Index("ix_test_suites_steps_gin", "steps", postgresql_using="gin"),
        Index("ix_test_suites_variables_gin", "variables", postgresql_using="gin"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        "project_id",
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    variables: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    queue_id: Mapped[uuid.UUID | None] = mapped_column(
        "queue_id",
        ForeignKey("execution_queues.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    agent_selection_policy: Mapped[AgentSelectionPolicy] = mapped_column(
        Enum(AgentSelectionPolicy, name="agent_selection_policy_enum", native_enum=True),
        nullable=False,
        default=AgentSelectionPolicy.ROUND_ROBIN,
        server_default=text("'round_robin'::agent_selection_policy_enum"),
    )
    agent_tags: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        "created_by",
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    project: Mapped["Project"] = relationship("Project", back_populates="test_suites")
    queue: Mapped["ExecutionQueue" | None] = relationship("ExecutionQueue", back_populates="test_suites")
    creator: Mapped["User"] = relationship("User", back_populates="test_suites_created")
