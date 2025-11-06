from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:
    from app.models.execution_queue import ExecutionQueue
    from app.models.project import Project

class ExecutionPolicy(BaseModel, Base):
    __tablename__ = "execution_policies"

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_execution_policies_project_name"),
        Index("ix_execution_policies_project_enabled", "project_id", "enabled"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    max_concurrency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_host_qps: Mapped[float | None] = mapped_column(Float, nullable=True)
    queue_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("execution_queues.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
        server_default=text("5"),
    )
    retry_max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        server_default=text("3"),
    )
    retry_backoff: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    timeout_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=30,
        server_default=text("30"),
    )
    circuit_breaker_threshold: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
        server_default=text("5"),
    )
    circuit_breaker_window_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=60,
        server_default=text("60"),
    )
    tags_include: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    tags_exclude: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("TRUE"),
    )

    project: Mapped[Project] = relationship(
        "Project",
        back_populates="execution_policies",
        foreign_keys=[project_id],
        primaryjoin="ExecutionPolicy.project_id == Project.id",
    )
    queue: Mapped[ExecutionQueue | None] = relationship("ExecutionQueue", back_populates="policies")

__all__ = ["ExecutionPolicy"]
