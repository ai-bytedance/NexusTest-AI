"""add issue sync state and integration webhooks

Revision ID: 202411090010
Revises: 202411080009
Create Date: 2024-11-09 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202411090010"
down_revision: str | None = "202411080009"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


issue_sync_state_enum = sa.Enum("ok", "error", name="issue_sync_state_enum")
integration_webhook_status_enum = sa.Enum(
    "pending",
    "processing",
    "processed",
    "failed",
    name="integration_webhook_status_enum",
)


def upgrade() -> None:
    bind = op.get_bind()
    issue_sync_state_enum.create(bind, checkfirst=True)
    integration_webhook_status_enum.create(bind, checkfirst=True)

    op.add_column(
        "issues",
        sa.Column(
            "sync_state",
            issue_sync_state_enum,
            nullable=False,
            server_default=sa.text("'ok'::issue_sync_state_enum"),
        ),
    )
    op.add_column("issues", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column(
        "issues",
        sa.Column("last_webhook_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "issues",
        sa.Column(
            "linked_prs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "issues",
        sa.Column(
            "linked_commits",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column("issues", "sync_state", server_default=None)
    op.alter_column("issues", "linked_prs", server_default=None)
    op.alter_column("issues", "linked_commits", server_default=None)

    op.create_table(
        "integration_webhooks",
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
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("signature", sa.String(length=512), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "headers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            integration_webhook_status_enum,
            nullable=False,
            server_default=sa.text("'pending'::integration_webhook_status_enum"),
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["integration_id"],
            ["integrations.id"],
            name=op.f("fk_integration_webhooks_integration_id_integrations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_integration_webhooks_project_id_projects"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_webhooks")),
        sa.UniqueConstraint(
            "provider",
            "idempotency_key",
            name=op.f("uq_integration_webhooks_provider_idempotency"),
        ),
    )
    op.create_index(
        op.f("ix_integration_webhooks_integration_id"),
        "integration_webhooks",
        ["integration_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_webhooks_provider"),
        "integration_webhooks",
        ["provider"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_webhooks_status"),
        "integration_webhooks",
        ["status"],
        unique=False,
    )
    op.alter_column(
        "integration_webhooks",
        "status",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_integration_webhooks_status"), table_name="integration_webhooks")
    op.drop_index(op.f("ix_integration_webhooks_provider"), table_name="integration_webhooks")
    op.drop_index(op.f("ix_integration_webhooks_integration_id"), table_name="integration_webhooks")
    op.drop_table("integration_webhooks")

    op.drop_column("issues", "linked_commits")
    op.drop_column("issues", "linked_prs")
    op.drop_column("issues", "last_webhook_at")
    op.drop_column("issues", "last_error")
    op.drop_column("issues", "sync_state")

    integration_webhook_status_enum.drop(op.get_bind(), checkfirst=True)
    issue_sync_state_enum.drop(op.get_bind(), checkfirst=True)
