from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel, UTC_NOW

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.test_report import TestReport


class AgentStatus(str, enum.Enum):
    OFFLINE = "offline"
    ONLINE = "online"
    DISABLED = "disabled"


class Agent(BaseModel, Base):
    __tablename__ = "agents"

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_agents_project_name"),
    )

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        "project_id",
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    env_tags: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    status: Mapped[AgentStatus] = mapped_column(
        Enum(AgentStatus, name="agent_status_enum", native_enum=True),
        nullable=False,
        default=AgentStatus.OFFLINE,
        server_default=text("'offline'::agent_status_enum"),
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    capabilities: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    token_last_rotated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=UTC_NOW,
    )
    last_seen_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_seen_user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    project: Mapped["Project" | None] = relationship("Project", back_populates="agents")
    reports: Mapped[list["TestReport"]] = relationship("TestReport", back_populates="agent")


__all__ = [
    "Agent",
    "AgentStatus",
]
