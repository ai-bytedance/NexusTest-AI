"""add issue tracking tables

Revision ID: 202411070008
Revises: 202411060007
Create Date: 2024-11-07 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202411070008"
down_revision: str | None = "202411060007"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


integration_provider_enum = sa.Enum(
    "jira",
    "linear",
    "github",
    name="integration_provider_enum",
)

issue_link_source_enum = sa.Enum(
    "manual",
    "auto",
    name="issue_link_source_enum",
)


def upgrade() -> None:
    bind = op.get_bind()
    integration_provider_enum.create(bind, checkfirst=True)
    issue_link_source_enum.create(bind, checkfirst=True)

    op.create_table(
        "integrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', NOW())"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', NOW())"),
        ),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("provider", integration_provider_enum, nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_integrations_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_integrations_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integrations")),
        sa.UniqueConstraint("project_id", "name", name=op.f("uq_integrations_project_name")),
    )
    op.create_index(op.f("ix_integrations_project_id"), "integrations", ["project_id"], unique=False)
    op.create_index("ix_integrations_provider", "integrations", ["provider"], unique=False)

    op.create_table(
        "issues",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', NOW())"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', NOW())"),
        ),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column(
            "status",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column("dedupe_key", sa.String(length=255), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_issues_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["integration_id"],
            ["integrations.id"],
            name=op.f("fk_issues_integration_id_integrations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_issues_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_issues")),
        sa.UniqueConstraint("provider", "external_id", name=op.f("uq_issues_provider_external")),
    )
    op.create_index(op.f("ix_issues_project_id"), "issues", ["project_id"], unique=False)
    op.create_index("ix_issues_provider", "issues", ["provider"], unique=False)
    op.create_index("ix_issues_dedupe_key", "issues", ["dedupe_key"], unique=False)

    op.create_table(
        "auto_ticket_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', NOW())"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', NOW())"),
        ),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "filters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "template",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "dedupe_window_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("60"),
        ),
        sa.Column(
            "reopen_if_recurs",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column(
            "close_after_success_runs",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_auto_ticket_rules_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["integration_id"],
            ["integrations.id"],
            name=op.f("fk_auto_ticket_rules_integration_id_integrations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_auto_ticket_rules_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auto_ticket_rules")),
        sa.UniqueConstraint("project_id", "name", name=op.f("uq_auto_ticket_rules_project_name")),
    )
    op.create_index(op.f("ix_auto_ticket_rules_project_id"), "auto_ticket_rules", ["project_id"], unique=False)
    op.create_index(
        op.f("ix_auto_ticket_rules_integration_id"),
        "auto_ticket_rules",
        ["integration_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_auto_ticket_rules_enabled"),
        "auto_ticket_rules",
        ["project_id", "enabled"],
        unique=False,
    )

    op.create_table(
        "report_issue_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', NOW())"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', NOW())"),
        ),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("linked_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "source",
            issue_link_source_enum,
            nullable=False,
            server_default=sa.text("'manual'::issue_link_source_enum"),
        ),
        sa.Column("note", sa.String(length=512), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["test_reports.id"],
            name=op.f("fk_report_issue_links_report_id_test_reports"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["issue_id"],
            ["issues.id"],
            name=op.f("fk_report_issue_links_issue_id_issues"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["linked_by"],
            ["users.id"],
            name=op.f("fk_report_issue_links_linked_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_report_issue_links")),
        sa.UniqueConstraint("report_id", "issue_id", name=op.f("uq_report_issue_link")),
    )
    op.create_index(op.f("ix_report_issue_links_report"), "report_issue_links", ["report_id"], unique=False)
    op.create_index(op.f("ix_report_issue_links_issue"), "report_issue_links", ["issue_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_report_issue_links_issue"), table_name="report_issue_links")
    op.drop_index(op.f("ix_report_issue_links_report"), table_name="report_issue_links")
    op.drop_table("report_issue_links")

    op.drop_index(op.f("ix_auto_ticket_rules_enabled"), table_name="auto_ticket_rules")
    op.drop_index(op.f("ix_auto_ticket_rules_integration_id"), table_name="auto_ticket_rules")
    op.drop_index(op.f("ix_auto_ticket_rules_project_id"), table_name="auto_ticket_rules")
    op.drop_table("auto_ticket_rules")

    op.drop_index("ix_issues_dedupe_key", table_name="issues")
    op.drop_index("ix_issues_provider", table_name="issues")
    op.drop_index(op.f("ix_issues_project_id"), table_name="issues")
    op.drop_table("issues")

    op.drop_index("ix_integrations_provider", table_name="integrations")
    op.drop_index(op.f("ix_integrations_project_id"), table_name="integrations")
    op.drop_table("integrations")

    issue_link_source_enum.drop(op.get_bind(), checkfirst=True)
    integration_provider_enum.drop(op.get_bind(), checkfirst=True)
