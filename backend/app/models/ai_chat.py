from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:  # pragma: no cover
    from app.models.project import Project
    from app.models.user import User


class AiChat(BaseModel, Base):
    __tablename__ = "ai_chats"

    project_id: Mapped[uuid.UUID] = mapped_column(
        "project_id",
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        "created_by",
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    project: Mapped["Project"] = relationship("Project", back_populates="ai_chats")
    creator: Mapped["User"] = relationship("User", back_populates="ai_chats_created")
    messages: Mapped[list["AiChatMessage"]] = relationship(
        "AiChatMessage",
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="AiChatMessage.sequence",
    )


class AiChatMessage(BaseModel, Base):
    __tablename__ = "ai_chat_messages"

    __table_args__ = (
        UniqueConstraint("chat_id", "sequence", name="uq_ai_chat_messages_chat_seq"),
    )

    chat_id: Mapped[uuid.UUID] = mapped_column(
        "chat_id",
        ForeignKey("ai_chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        "author_id",
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    content: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    tool_invoked: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)

    chat: Mapped["AiChat"] = relationship("AiChat", back_populates="messages")
    author: Mapped["User" | None] = relationship("User", back_populates="ai_chat_messages")


__all__ = ["AiChat", "AiChatMessage"]
