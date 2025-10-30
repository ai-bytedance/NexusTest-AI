from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Enum, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel
from app.models.execution_routing import AgentSelectionPolicy

if TYPE_CHECKING:
    from app.models.api import Api
    from app.models.dataset import Dataset
    from app.models.environment import Environment
    from app.models.execution_policy import ExecutionPolicy
    from app.models.execution_queue import ExecutionQueue
    from app.models.project import Project
    from app.models.user import User


class TestCase(BaseModel, Base):
    __tablename__ = "test_cases"

    __table_args__ = (
        Index("ix_test_cases_inputs_gin", "inputs", postgresql_using="gin"),
        Index("ix_test_cases_expected_gin", "expected", postgresql_using="gin"),
        Index("ix_test_cases_assertions_gin", "assertions", postgresql_using="gin"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        "project_id",
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_id: Mapped[uuid.UUID] = mapped_column(
        "api_id",
        ForeignKey("apis.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    expected: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    assertions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    environment_id: Mapped[uuid.UUID | None] = mapped_column(
        "environment_id",
        ForeignKey("environments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        "dataset_id",
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    queue_id: Mapped[uuid.UUID | None] = mapped_column(
        "queue_id",
        ForeignKey("execution_queues.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        "policy_id",
        ForeignKey("execution_policies.id", ondelete="SET NULL"),
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
    param_mapping: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("TRUE"),
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        "created_by",
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    project: Mapped["Project"] = relationship("Project", back_populates="test_cases")
    api: Mapped["Api"] = relationship("Api", back_populates="test_cases")
    environment: Mapped["Environment | None"] = relationship("Environment", back_populates="test_cases")
    dataset: Mapped["Dataset | None"] = relationship("Dataset", back_populates="test_cases")
    queue: Mapped["ExecutionQueue" | None] = relationship("ExecutionQueue", back_populates="test_cases")
    policy: Mapped["ExecutionPolicy" | None] = relationship("ExecutionPolicy")
    creator: Mapped["User"] = relationship("User", back_populates="test_cases_created")
