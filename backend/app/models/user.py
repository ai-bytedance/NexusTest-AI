from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:
    from app.models.dataset import Dataset
    from app.models.environment import Environment
    from app.models.execution_plan import ExecutionPlan
    from app.models.notifier import Notifier
    from app.models.project import Project
    from app.models.project_member import ProjectMember
    from app.models.test_case import TestCase
    from app.models.test_suite import TestSuite


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MEMBER = "member"


class User(BaseModel, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum", native_enum=True),
        nullable=False,
        default=UserRole.MEMBER,
        server_default=text("'member'::user_role_enum"),
    )

    projects_created: Mapped[list["Project"]] = relationship("Project", back_populates="creator")
    memberships: Mapped[list["ProjectMember"]] = relationship(
        "ProjectMember",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    test_cases_created: Mapped[list["TestCase"]] = relationship("TestCase", back_populates="creator")
    test_suites_created: Mapped[list["TestSuite"]] = relationship("TestSuite", back_populates="creator")
    environments_created: Mapped[list["Environment"]] = relationship(
        "Environment",
        back_populates="creator",
    )
    datasets_created: Mapped[list["Dataset"]] = relationship(
        "Dataset",
        back_populates="creator",
    )
    execution_plans_created: Mapped[list["ExecutionPlan"]] = relationship(
        "ExecutionPlan",
        back_populates="creator",
    )
    notifiers_created: Mapped[list["Notifier"]] = relationship(
        "Notifier",
        back_populates="creator",
    )
