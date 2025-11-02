"""Add webhooks v2 with signed callbacks and delivery console

Revision ID: 202411130014
Revises: 202411120013
Create Date: 2024-11-13 10:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202411130014"
down_revision: str | None = "202411120013"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None

# Webhook event types
WEBHOOK_EVENT_TYPES = (
    "run.started",
    "run.finished",
    "import.diff_ready",
    "import.applied",
    "issue.created",
    "issue.updated",
)

# Webhook delivery statuses
WEBHOOK_DELIVERY_STATUSES = (
    "pending",
    "delivered",
    "failed",
    "dlq",
)

# Webhook backoff strategies
WEBHOOK_BACKOFF_STRATEGIES = (
    "exponential",
    "linear",
    "fixed",
)

webhook_backoff_strategy_enum = sa.Enum(
    *WEBHOOK_BACKOFF_STRATEGIES,
    name="webhook_backoff_strategy",
    create_type=False,
)
webhook_delivery_status_enum = sa.Enum(
    *WEBHOOK_DELIVERY_STATUSES,
    name="webhook_delivery_status",
    create_type=False,
)
webhook_event_type_enum = sa.Enum(
    *WEBHOOK_EVENT_TYPES,
    name="webhook_event_type",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_type t
                JOIN pg_namespace n ON n.oid = t.typnamespace
                WHERE t.typname = 'webhook_backoff_strategy' AND n.nspname = 'public'
            ) THEN
                CREATE TYPE webhook_backoff_strategy AS ENUM ('exponential', 'linear', 'fixed');
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
                WHERE t.typname = 'webhook_delivery_status' AND n.nspname = 'public'
            ) THEN
                CREATE TYPE webhook_delivery_status AS ENUM ('pending', 'delivered', 'failed', 'dlq');
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
                WHERE t.typname = 'webhook_event_type' AND n.nspname = 'public'
            ) THEN
                CREATE TYPE webhook_event_type AS ENUM ('run.started', 'run.finished', 'import.diff_ready', 'import.applied', 'issue.created', 'issue.updated');
            END IF;
        END
        $$;
        """
    )

    op.create_table(
        "webhook_subscriptions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            primary_key=True,
            default=sa.text("gen_random_uuid()"),
        ),
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
            default=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("secret", sa.String(length=255), nullable=False),
        sa.Column(
            "events",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            default=True,
            server_default=sa.text("TRUE"),
        ),
        sa.Column(
            "headers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "retries_max",
            sa.Integer(),
            nullable=False,
            default=5,
            server_default=sa.text("5"),
        ),
        sa.Column(
            "backoff_strategy",
            webhook_backoff_strategy_enum,
            nullable=False,
            default="exponential",
            server_default=sa.text("'exponential'::webhook_backoff_strategy"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.Index("ix_webhook_subscriptions_project_id", "project_id"),
        sa.Index("ix_webhook_subscriptions_created_by", "created_by"),
    )

    # Create webhook_deliveries table
    op.create_table(
        "webhook_deliveries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            primary_key=True,
            default=sa.text("gen_random_uuid()"),
        ),
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
            default=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            webhook_event_type_enum,
            nullable=False,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "status",
            webhook_delivery_status_enum,
            nullable=False,
            default="pending",
            server_default=sa.text("'pending'::webhook_delivery_status"),
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            default=0,
            server_default=sa.text("0"),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["webhook_subscriptions.id"],
            ondelete="CASCADE",
        ),
        sa.Index("ix_webhook_deliveries_subscription_id", "subscription_id"),
        sa.Index("ix_webhook_deliveries_event_type", "event_type"),
        sa.Index("ix_webhook_deliveries_status", "status"),
        sa.Index("ix_webhook_deliveries_next_retry_at", "next_retry_at"),
        sa.Index("ix_webhook_deliveries_delivered_at", "delivered_at"),
    )


def downgrade() -> None:
    op.drop_table("webhook_deliveries")
    op.drop_table("webhook_subscriptions")
    op.execute("DROP TYPE IF EXISTS webhook_event_type")
    op.execute("DROP TYPE IF EXISTS webhook_delivery_status")
    op.execute("DROP TYPE IF EXISTS webhook_backoff_strategy")