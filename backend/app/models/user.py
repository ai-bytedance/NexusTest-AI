from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:
    from app.models.ai_chat import AiChat, AiChatMessage
    from app.models.api_token import ApiToken
    from app.models.dataset import Dataset
    from app.models.environment import Environment
    from app.models.execution_plan import ExecutionPlan
    from app.models.integration import Integration
    from app.models.issue import Issue, ReportIssueLink
    from app.models.notifier import Notifier
    from app.models.project import Project
    from app.models.project_member import ProjectMember
    from app.models.auto_ticket_rule import AutoTicketRule
    from app.models.test_case import TestCase
    from app.models.test_suite import TestSuite
    from app.models.organization import OrganizationMembership
    from app.models.team_membership import TeamMembership
    from app.models.user_identity import UserIdentity


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
    failed_login_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    projects_created: Mapped[list[Project]] = relationship("Project", back_populates="creator")
    ai_chats_created: Mapped[list[AiChat]] = relationship("AiChat", back_populates="creator")
    ai_chat_messages: Mapped[list[AiChatMessage]] = relationship("AiChatMessage", back_populates="author")
    memberships: Mapped[list[ProjectMember]] = relationship(
        "ProjectMember",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    api_tokens: Mapped[list[ApiToken]] = relationship(
        "ApiToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    test_cases_created: Mapped[list[TestCase]] = relationship("TestCase", back_populates="creator")
    test_suites_created: Mapped[list[TestSuite]] = relationship("TestSuite", back_populates="creator")
    environments_created: Mapped[list[Environment]] = relationship(
        "Environment",
        back_populates="creator",
    )
    datasets_created: Mapped[list[Dataset]] = relationship(
        "Dataset",
        back_populates="creator",
    )
    execution_plans_created: Mapped[list[ExecutionPlan]] = relationship(
        "ExecutionPlan",
        back_populates="creator",
    )
    notifiers_created: Mapped[list[Notifier]] = relationship(
        "Notifier",
        back_populates="creator",
    )
    integrations_created: Mapped[list[Integration]] = relationship(
        "Integration",
        back_populates="creator",
    )
    issues_created: Mapped[list[Issue]] = relationship(
        "Issue",
        back_populates="creator",
    )
    issue_links_created: Mapped[list[ReportIssueLink]] = relationship(
        "ReportIssueLink",
        back_populates="linker",
    )
    auto_ticket_rules_created: Mapped[list[AutoTicketRule]] = relationship(
        "AutoTicketRule",
        back_populates="creator",
    )
    organization_memberships: Mapped[list[OrganizationMembership]] = relationship(
        "OrganizationMembership",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    team_memberships: Mapped[list[TeamMembership]] = relationship(
        "TeamMembership",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    identities: Mapped[list[UserIdentity]] = relationship(
        "UserIdentity",
        back_populates="user",
        cascade="all, delete-orphan",
    )
