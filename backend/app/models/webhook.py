from __future__ import annotations

import uuid
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class WebhookEventType(str, Enum):
    RUN_STARTED = "run.started"
    RUN_FINISHED = "run.finished"
    IMPORT_DIFF_READY = "import.diff_ready"
    IMPORT_APPLIED = "import.applied"
    ISSUE_CREATED = "issue.created"
    ISSUE_UPDATED = "issue.updated"

    @classmethod
    def all_values(cls) -> list[str]:
        return [event.value for event in cls]


class WebhookDeliveryStatus(str, Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    DLQ = "dlq"


class WebhookBackoffStrategy(str, Enum):
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIXED = "fixed"


class WebhookSubscription(BaseModel, Base):
    __tablename__ = "webhook_subscriptions"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    secret: Mapped[str] = mapped_column(String(255), nullable=False)
    events: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    enabled: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default=text("TRUE"),
    )
    headers: Mapped[dict[str, str]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    retries_max: Mapped[int] = mapped_column(
        nullable=False,
        default=5,
        server_default=text("5"),
    )
    backoff_strategy: Mapped[WebhookBackoffStrategy] = mapped_column(
        nullable=False,
        default=WebhookBackoffStrategy.EXPONENTIAL,
        server_default=text("'exponential'::webhook_backoff_strategy"),
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    project: Mapped["Project"] = relationship("Project", back_populates="webhook_subscriptions")
    creator: Mapped["User"] = relationship("User")
    deliveries: Mapped[list["WebhookDelivery"]] = relationship(
        "WebhookDelivery",
        back_populates="subscription",
        cascade="all, delete-orphan",
    )


class WebhookDelivery(BaseModel, Base):
    __tablename__ = "webhook_deliveries"

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[WebhookEventType] = mapped_column(
        nullable=False,
        index=True,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )
    status: Mapped[WebhookDeliveryStatus] = mapped_column(
        nullable=False,
        default=WebhookDeliveryStatus.PENDING,
        server_default=text("'pending'::webhook_delivery_status"),
        index=True,
    )
    attempts: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True,
        index=True,
    )
    delivered_at: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True,
        index=True,
    )

    subscription: Mapped["WebhookSubscription"] = relationship(
        "WebhookSubscription",
        back_populates="deliveries",
    )