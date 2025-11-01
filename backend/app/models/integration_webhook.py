from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.integration import Integration
    from app.models.project import Project

class IntegrationWebhookStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"

class IntegrationWebhook(BaseModel, Base):
    __tablename__ = "integration_webhooks"

    __table_args__ = (
        Index("ix_integration_webhooks_integration_id", "integration_id"),
        Index("ix_integration_webhooks_provider", "provider"),
        Index("ix_integration_webhooks_status", "status"),
        UniqueConstraint(
            "provider",
            "idempotency_key",
            name="uq_integration_webhooks_provider_idempotency",
        ),
    )

    integration_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("integrations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    signature: Mapped[str | None] = mapped_column(String(512), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    headers: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[IntegrationWebhookStatus] = mapped_column(
        Enum(IntegrationWebhookStatus, name="integration_webhook_status_enum", native_enum=True),
        nullable=False,
        default=IntegrationWebhookStatus.PENDING,
        server_default=text("'pending'::integration_webhook_status_enum"),
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    integration: Mapped[Integration | None] = relationship("Integration", back_populates="webhooks")
    project: Mapped[Project | None] = relationship("Project", back_populates="integration_webhooks")

if not TYPE_CHECKING:  # pragma: no cover - runtime typing support
    from app.models.integration import Integration  # noqa: F401
    from app.models.project import Project  # noqa: F401

__all__ = ["IntegrationWebhook", "IntegrationWebhookStatus"]
