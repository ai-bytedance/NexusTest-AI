"""Add execution plans and notifier models

Revision ID: 202410290002
Revises: 202410280001
Create Date: 2024-10-29 03:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202410290002"
down_revision: str | None = "202410280001"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None

execution_plan_type_enum = sa.Enum("cron", "interval", name="execution_plan_type_enum", create_type=False)
notifier_type_enum = sa.Enum("webhook", "feishu", "slack", name="notifier_type_enum", create_type=False)
notifier_event_type_enum = sa.Enum("run_finished", name="notifier_event_type_enum", create_type=False)
notifier_event_status_enum = sa.Enum("pending", "success", "failed", name="notifier_event_status_enum", create_type=False)


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_type t
                JOIN pg_namespace n ON n.oid = t.typnamespace
                WHERE t.typname = 'execution_plan_type_enum' AND n.nspname = 'public'
            ) THEN
                CREATE TYPE execution_plan_type_enum AS ENUM ('cron', 'interval');
            END IF;
        END
        $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_type t
                JOIN pg_namespace n ON n.oid = t.typnamespace
                WHERE t.typname = 'notifier_type_enum' AND n.nspname = 'public'
            ) THEN
                CREATE TYPE notifier_type_enum AS ENUM ('webhook', 'feishu', 'slack');
            END IF;
        END
        $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_type t
                JOIN pg_namespace n ON n.oid = t.typnamespace
                WHERE t.typname = 'notifier_event_type_enum' AND n.nspname = 'public'
            ) THEN
                CREATE TYPE notifier_event_type_enum AS ENUM ('run_finished');
            END IF;
        END
        $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_type t
                JOIN pg_namespace n ON n.oid = t.typnamespace
                WHERE t.typname = 'notifier_event_status_enum' AND n.nspname = 'public'
            ) THEN
                CREATE TYPE notifier_event_status_enum AS ENUM ('pending', 'success', 'failed');
            END IF;
        END
        $$;
        """
    )

    op.create_table(
        "execution_plans",
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
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", execution_plan_type_enum, nullable=False),
        sa.Column("cron_expr", sa.String(length=255), nullable=True),
        sa.Column("interval_seconds", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default=sa.text("'UTC'")),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_execution_plans_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_execution_plans_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_execution_plans")),
        sa.UniqueConstraint("project_id", "name", name="uq_execution_plans_project_name"),
    )
    op.create_index(
        op.f("ix_execution_plans_project_enabled"),
        "execution_plans",
        ["project_id", "enabled"],
        unique=False,
    )
    op.create_index(
        op.f("ix_execution_plans_next_run_at"),
        "execution_plans",
        ["next_run_at"],
        unique=False,
    )
    op.create_index(
        "ix_execution_plans_config_gin",
        "execution_plans",
        ["config"],
        unique=False,
        postgresql_using="gin",
    )

    op.create_table(
        "notifiers",
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
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", notifier_type_enum, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_notifiers_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_notifiers_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifiers")),
        sa.UniqueConstraint("project_id", "name", name="uq_notifiers_project_name"),
    )
    op.create_index(op.f("ix_notifiers_project_id"), "notifiers", ["project_id"], unique=False)
    op.create_index(op.f("ix_notifiers_type"), "notifiers", ["type"], unique=False)

    op.create_table(
        "notifier_events",
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
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notifier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event", notifier_event_type_enum, nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            notifier_event_status_enum,
            nullable=False,
            server_default=sa.text("'pending'::notifier_event_status_enum"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["notifier_id"],
            ["notifiers.id"],
            name=op.f("fk_notifier_events_notifier_id_notifiers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_notifier_events_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifier_events")),
    )
    op.create_index(op.f("ix_notifier_events_project_id"), "notifier_events", ["project_id"], unique=False)
    op.create_index(op.f("ix_notifier_events_status"), "notifier_events", ["status"], unique=False)
    op.create_index(op.f("ix_notifier_events_created_at"), "notifier_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_notifier_events_created_at"), table_name="notifier_events")
    op.drop_index(op.f("ix_notifier_events_status"), table_name="notifier_events")
    op.drop_index(op.f("ix_notifier_events_project_id"), table_name="notifier_events")
    op.drop_table("notifier_events")

    op.drop_index(op.f("ix_notifiers_type"), table_name="notifiers")
    op.drop_index(op.f("ix_notifiers_project_id"), table_name="notifiers")
    op.drop_table("notifiers")

    op.drop_index("ix_execution_plans_config_gin", table_name="execution_plans")
    op.drop_index(op.f("ix_execution_plans_next_run_at"), table_name="execution_plans")
    op.drop_index(op.f("ix_execution_plans_project_enabled"), table_name="execution_plans")
    op.drop_table("execution_plans")

    op.execute("DROP TYPE IF EXISTS notifier_event_status_enum")
    op.execute("DROP TYPE IF EXISTS notifier_event_type_enum")
    op.execute("DROP TYPE IF EXISTS notifier_type_enum")
    op.execute("DROP TYPE IF EXISTS execution_plan_type_enum")
