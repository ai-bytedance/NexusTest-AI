from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class TestSuite(BaseModel, Base):
    __tablename__ = "test_suites"

    __table_args__ = (
        Index("ix_test_suites_steps_gin", "steps", postgresql_using="gin"),
        Index("ix_test_suites_variables_gin", "variables", postgresql_using="gin"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        "project_id",
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    variables: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_by: Mapped[uuid.UUID] = mapped_column(
        "created_by",
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    project: Mapped["Project"] = relationship("Project", back_populates="test_suites")
    creator: Mapped["User"] = relationship("User", back_populates="test_suites_created")
