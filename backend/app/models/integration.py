from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Enum, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:
    from app.models.auto_ticket_rule import AutoTicketRule
    from app.models.integration_webhook import IntegrationWebhook
    from app.models.issue import Issue
    from app.models.project import Project
    from app.models.user import User


class IntegrationProvider(str, enum.Enum):
    JIRA = "jira"
    LINEAR = "linear"
    GITHUB = "github"


class Integration(BaseModel, Base):
    __tablename__ = "integrations"

    __table_args__ = (
        Index("ix_integrations_project_id", "project_id"),
        Index("ix_integrations_provider", "provider"),
        UniqueConstraint("project_id", "name", name="uq_integrations_project_name"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[IntegrationProvider] = mapped_column(
        Enum(IntegrationProvider, name="integration_provider_enum", native_enum=True),
        nullable=False,
    )
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    project: Mapped[Project] = relationship("Project", back_populates="integrations")
    creator: Mapped[User] = relationship("User", back_populates="integrations_created")
    ticket_rules: Mapped[list[AutoTicketRule]] = relationship(
        "AutoTicketRule",
        back_populates="integration",
        cascade="all, delete-orphan",
    )
    issues: Mapped[list[Issue]] = relationship(
        "Issue",
        back_populates="integration",
        cascade="all, delete-orphan",
    )
    webhooks: Mapped[list[IntegrationWebhook]] = relationship(
        "IntegrationWebhook",
        back_populates="integration",
        cascade="all, delete-orphan",
    )


__all__ = ["Integration", "IntegrationProvider"]
