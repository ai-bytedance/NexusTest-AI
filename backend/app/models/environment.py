from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:
    from app.models.execution_policy import ExecutionPolicy
    from app.models.execution_queue import ExecutionQueue
    from app.models.project import Project
    from app.models.test_case import TestCase
    from app.models.user import User


class Environment(BaseModel, Base):
    __tablename__ = "environments"

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_environments_project_name"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        "project_id",
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    headers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    variables: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    secrets: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("FALSE"),
    )
    default_queue_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("execution_queues.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    default_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("execution_policies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        "created_by",
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    project: Mapped["Project"] = relationship("Project", back_populates="environments")
    creator: Mapped["User"] = relationship("User", back_populates="environments_created")
    test_cases: Mapped[list["TestCase"]] = relationship("TestCase", back_populates="environment")
    queues: Mapped[list["ExecutionQueue"]] = relationship(
        "ExecutionQueue",
        back_populates="environment",
        cascade="all, delete-orphan",
    )
    default_queue: Mapped["ExecutionQueue" | None] = relationship(
        "ExecutionQueue",
        foreign_keys=[default_queue_id],
        post_update=True,
    )
    default_policy: Mapped["ExecutionPolicy" | None] = relationship(
        "ExecutionPolicy",
        foreign_keys=[default_policy_id],
        post_update=True,
    )

__all__ = ["Environment"]
