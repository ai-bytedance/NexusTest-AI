from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Enum, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:
    from app.models.notifier_event import NotifierEvent
    from app.models.project import Project
    from app.models.user import User


class NotifierType(str, enum.Enum):
    WEBHOOK = "webhook"
    FEISHU = "feishu"
    SLACK = "slack"
    WECOM = "wecom"
    DINGTALK = "dingtalk"


class Notifier(BaseModel, Base):
    __tablename__ = "notifiers"

    __table_args__ = (
        Index("ix_notifiers_project_id", "project_id"),
        Index("ix_notifiers_type", "type"),
        UniqueConstraint("project_id", "name", name="uq_notifiers_project_name"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[NotifierType] = mapped_column(
        Enum(NotifierType, name="notifier_type_enum", native_enum=True),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
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

    project: Mapped["Project"] = relationship("Project", back_populates="notifiers")
    creator: Mapped["User"] = relationship("User", back_populates="notifiers_created")
    events: Mapped[list["NotifierEvent"]] = relationship(
        "NotifierEvent",
        back_populates="notifier",
        cascade="all, delete-orphan",
    )


__all__ = ["Notifier", "NotifierType"]
