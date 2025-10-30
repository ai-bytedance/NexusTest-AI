from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel

if TYPE_CHECKING:
    from app.models.agent import Agent, AgentAlertThreshold
    from app.models.ai_chat import AiChat
    from app.models.ai_task import AITask
    from app.models.api import Api
    from app.models.dataset import Dataset
    from app.models.environment import Environment
    from app.models.execution_plan import ExecutionPlan
    from app.models.execution_policy import ExecutionPolicy
    from app.models.execution_queue import ExecutionQueue
    from app.models.import_source import ImportRun, ImportSource
    from app.models.integration import Integration
    from app.models.integration_webhook import IntegrationWebhook
    from app.models.issue import Issue
    from app.models.notifier import Notifier
    from app.models.notifier_event import NotifierEvent
    from app.models.organization import Organization
    from app.models.auto_ticket_rule import AutoTicketRule
    from app.models.project_member import ProjectMember
    from app.models.project_team_role import ProjectTeamRole
    from app.models.rate_limit_policy import RateLimitPolicy
    from app.models.test_case import TestCase
    from app.models.test_report import TestReport
    from app.models.test_suite import TestSuite
    from app.models.user import User
    from app.models.webhook import WebhookSubscription


class Project(BaseModel, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    key: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        "created_by",
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    default_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("execution_policies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    default_queue_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("execution_queues.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    default_rate_limit_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rate_limit_policies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    notification_settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    organization: Mapped["Organization" | None] = relationship("Organization", back_populates="projects")
    creator: Mapped["User"] = relationship("User", back_populates="projects_created")
    members: Mapped[list["ProjectMember"]] = relationship(
        "ProjectMember",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    apis: Mapped[list["Api"]] = relationship("Api", back_populates="project", cascade="all, delete-orphan")
    environments: Mapped[list["Environment"]] = relationship(
        "Environment",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    datasets: Mapped[list["Dataset"]] = relationship(
        "Dataset",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    queues: Mapped[list["ExecutionQueue"]] = relationship(
        "ExecutionQueue",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    agents: Mapped[list["Agent"]] = relationship(
        "Agent",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    agent_thresholds: Mapped[list["AgentAlertThreshold"]] = relationship(
        "AgentAlertThreshold",
        back_populates="project",
        cascade="all, delete-orphan",
    )
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
    ai_chats: Mapped[list["AiChat"]] = relationship(
        "AiChat", back_populates="project", cascade="all, delete-orphan"
    )
    execution_plans: Mapped[list["ExecutionPlan"]] = relationship(
        "ExecutionPlan",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    execution_policies: Mapped[list["ExecutionPolicy"]] = relationship(
        "ExecutionPolicy",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    rate_limit_policies: Mapped[list["RateLimitPolicy"]] = relationship(
        "RateLimitPolicy",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    notifiers: Mapped[list["Notifier"]] = relationship(
        "Notifier",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    notifier_events: Mapped[list["NotifierEvent"]] = relationship(
        "NotifierEvent",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    integrations: Mapped[list["Integration"]] = relationship(
        "Integration",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    issues: Mapped[list["Issue"]] = relationship(
        "Issue",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    integration_webhooks: Mapped[list["IntegrationWebhook"]] = relationship(
        "IntegrationWebhook",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    auto_ticket_rules: Mapped[list["AutoTicketRule"]] = relationship(
        "AutoTicketRule",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    import_sources: Mapped[list["ImportSource"]] = relationship(
        "ImportSource",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    import_runs: Mapped[list["ImportRun"]] = relationship(
        "ImportRun",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    team_roles: Mapped[list["ProjectTeamRole"]] = relationship(
        "ProjectTeamRole",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    default_policy: Mapped["ExecutionPolicy" | None] = relationship(
        "ExecutionPolicy",
        foreign_keys=[default_policy_id],
        post_update=True,
    )
    default_queue: Mapped["ExecutionQueue" | None] = relationship(
        "ExecutionQueue",
        foreign_keys=[default_queue_id],
        post_update=True,
    )
    default_rate_limit_policy: Mapped["RateLimitPolicy" | None] = relationship(
        "RateLimitPolicy",
        foreign_keys=[default_rate_limit_policy_id],
        post_update=True,
    )
    webhook_subscriptions: Mapped[list["WebhookSubscription"]] = relationship(
        "WebhookSubscription",
        back_populates="project",
        cascade="all, delete-orphan",
    )
