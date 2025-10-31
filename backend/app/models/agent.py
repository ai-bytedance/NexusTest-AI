from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel, UTC_NOW

if TYPE_CHECKING:
    from app.models.environment import Environment
    from app.models.execution_queue import ExecutionQueue
    from app.models.project import Project
    from app.models.test_report import TestReport

class AgentStatus(str, enum.Enum):
    OFFLINE = "offline"
    ONLINE = "online"
    DEGRADED = "degraded"
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
    environment_id: Mapped[uuid.UUID | None] = mapped_column(
        "environment_id",
        ForeignKey("environments.id", ondelete="SET NULL"),
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
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("TRUE"),
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_cpu_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_memory_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_load_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_queue_depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capabilities: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    health_metadata: Mapped[dict[str, Any]] = mapped_column(
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
    token_revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_seen_user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    project: Mapped[Project | None] = relationship("Project", back_populates="agents")
    environment: Mapped[Environment | None] = relationship("Environment", back_populates="agents")
    reports: Mapped[list[TestReport]] = relationship("TestReport", back_populates="agent")
    heartbeats: Mapped[list[AgentHeartbeat]] = relationship(
        "AgentHeartbeat",
        back_populates="agent",
        cascade="all, delete-orphan",
        order_by="AgentHeartbeat.recorded_at.desc()",
    )
    queue_memberships: Mapped[list[AgentQueueMembership]] = relationship(
        "AgentQueueMembership",
        back_populates="agent",
        cascade="all, delete-orphan",
    )
    alert_states: Mapped[list[AgentAlertState]] = relationship(
        "AgentAlertState",
        back_populates="agent",
        cascade="all, delete-orphan",
    )

class AgentHeartbeat(Base):
    __tablename__ = "agent_heartbeats"

    __table_args__ = (
        Index("ix_agent_heartbeats_agent_id", "agent_id"),
        Index("ix_agent_heartbeats_recorded_at", "recorded_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=UTC_NOW,
    )
    cpu_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    load_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    queue_depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    agent: Mapped[Agent] = relationship("Agent", back_populates="heartbeats")

class AgentQueueMembership(BaseModel, Base):
    __tablename__ = "agent_queue_memberships"

    __table_args__ = (
        UniqueConstraint("agent_id", "queue_id", name="uq_agent_queue_memberships_agent_queue"),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    queue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("execution_queues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    agent: Mapped[Agent] = relationship("Agent", back_populates="queue_memberships")
    queue: Mapped[ExecutionQueue] = relationship("ExecutionQueue", back_populates="agent_memberships")

class AgentAlertKind(str, enum.Enum):
    OFFLINE = "offline"
    BACKLOG = "backlog"
    LATENCY = "latency"

class AgentAlertThreshold(BaseModel, Base):
    __tablename__ = "agent_alert_thresholds"

    __table_args__ = (
        UniqueConstraint("project_id", "environment_id", name="uq_agent_alert_thresholds_scope"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    environment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    offline_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=120, server_default=text("120"))
    backlog_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=25, server_default=text("25"))
    latency_threshold_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=1000, server_default=text("1000"))
    metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    project: Mapped[Project] = relationship("Project", back_populates="agent_thresholds")
    environment: Mapped[Environment | None] = relationship("Environment", back_populates="agent_thresholds")

class AgentAlertState(BaseModel, Base):
    __tablename__ = "agent_alert_states"

    __table_args__ = (
        UniqueConstraint("agent_id", "kind", name="uq_agent_alert_states_agent_kind"),
        Index("ix_agent_alert_states_active", "active"),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[AgentAlertKind] = mapped_column(
        Enum(AgentAlertKind, name="agent_alert_kind_enum", native_enum=True),
        nullable=False,
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("FALSE"))
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    context: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    agent: Mapped[Agent] = relationship("Agent", back_populates="alert_states")

__all__ = [
    "Agent",
    "AgentStatus",
    "AgentHeartbeat",
    "AgentQueueMembership",
    "AgentAlertKind",
    "AgentAlertThreshold",
    "AgentAlertState",
]
