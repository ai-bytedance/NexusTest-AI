from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:
    from app.models.ai_task import AITask
    from app.models.api import Api
    from app.models.test_case import TestCase
    from app.models.test_report import TestReport
    from app.models.test_suite import TestSuite
    from app.models.user import User


class Project(BaseModel, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    key: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        "created_by",
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    creator: Mapped["User"] = relationship("User", back_populates="projects_created")
    apis: Mapped[list["Api"]] = relationship("Api", back_populates="project", cascade="all, delete-orphan")
    test_cases: Mapped[list["TestCase"]] = relationship(
        "TestCase", back_populates="project", cascade="all, delete-orphan"
    )
    test_suites: Mapped[list["TestSuite"]] = relationship(
        "TestSuite", back_populates="project", cascade="all, delete-orphan"
    )
    test_reports: Mapped[list["TestReport"]] = relationship(
        "TestReport", back_populates="project", cascade="all, delete-orphan"
    )
    ai_tasks: Mapped[list["AITask"]] = relationship(
        "AITask", back_populates="project", cascade="all, delete-orphan"
    )
