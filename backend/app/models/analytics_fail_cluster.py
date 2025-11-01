from __future__ import annotations

import enum
import uuid
from datetime import datetime as DateTimePy

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BaseModel


class AnalyticsFailClusterStatus(str, enum.Enum):
    OPEN = "open"
    MUTED = "muted"
    RESOLVED = "resolved"


class AnalyticsFailCluster(BaseModel, Base):
    __tablename__ = "analytics_fail_clusters"

    __table_args__ = (
        Index("ix_analytics_fail_clusters_project_signature", "project_id", "signature_hash", unique=True),
        Index("ix_analytics_fail_clusters_project_status", "project_id", "status"),
        Index("ix_analytics_fail_clusters_last_seen", "project_id", "last_seen_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    signature_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    sample_report_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    first_seen_at: Mapped[DateTimePy] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("TIMEZONE('utc', NOW())"),
    )
    last_seen_at: Mapped[DateTimePy] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("TIMEZONE('utc', NOW())"),
        onupdate=func.now(),
    )
    status: Mapped[AnalyticsFailClusterStatus] = mapped_column(
        Enum(AnalyticsFailClusterStatus, name="analytics_fail_cluster_status_enum", native_enum=True),
        nullable=False,
        default=AnalyticsFailClusterStatus.OPEN,
        server_default=text("'open'::analytics_fail_cluster_status_enum"),
    )
