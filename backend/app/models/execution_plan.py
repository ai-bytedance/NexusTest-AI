from __future__ import annotations

import enum
import uuid
from datetime import datetime as DateTimePy
from typing import TYPE_CHECKING, Any, Iterable

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class ExecutionPlanType(str, enum.Enum):
    CRON = "cron"
    INTERVAL = "interval"


class ExecutionPlan(BaseModel, Base):
    __tablename__ = "execution_plans"

    __table_args__ = (
        Index("ix_execution_plans_project_enabled", "project_id", "enabled"),
        Index("ix_execution_plans_next_run_at", "next_run_at"),
        Index("ix_execution_plans_config_gin", "config", postgresql_using="gin"),
        UniqueConstraint("project_id", "name", name="uq_execution_plans_project_name"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[ExecutionPlanType] = mapped_column(
        Enum(ExecutionPlanType, name="execution_plan_type_enum", native_enum=True),
        nullable=False,
    )
    cron_expr: Mapped[str | None] = mapped_column(String(255), nullable=True)
    interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'UTC'"))
    last_run_at: Mapped[DateTimePy | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[DateTimePy | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    project: Mapped[Project] = relationship("Project", back_populates="execution_plans")
    creator: Mapped[User] = relationship("User", back_populates="execution_plans_created")

    def set_suite_ids(self, suite_ids: Iterable[uuid.UUID | str]) -> None:
        payload = list(suite_ids)
        normalized: list[str] = []
        for value in payload:
            try:
                normalized.append(str(uuid.UUID(str(value))))
            except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
                raise ValueError(f"Invalid suite id: {value}") from exc
        config = dict(self.config or {})
        config["suite_ids"] = normalized
        self.config = config

    def add_suite_id(self, suite_id: uuid.UUID | str) -> None:
        existing = {str(item) for item in self.config.get("suite_ids", []) if item}
        try:
            normalized = str(uuid.UUID(str(suite_id)))
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise ValueError(f"Invalid suite id: {suite_id}") from exc
        existing.add(normalized)
        config = dict(self.config or {})
        config["suite_ids"] = list(existing)
        self.config = config

    @property
    def suite_ids(self) -> list[uuid.UUID]:
        raw = self.config.get("suite_ids") if isinstance(self.config, dict) else None
        if not isinstance(raw, list):
            return []
        suite_ids: list[uuid.UUID] = []
        for value in raw:
            try:
                suite_ids.append(uuid.UUID(str(value)))
            except (TypeError, ValueError):
                continue
        return suite_ids


__all__ = ["ExecutionPlan", "ExecutionPlanType"]
