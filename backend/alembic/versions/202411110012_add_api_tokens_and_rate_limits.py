"""Add API tokens and rate limiting policies

Revision ID: 202411110012
Revises: 202411100011
Create Date: 2024-11-11 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202411110012"
down_revision: str | None = "202411100011"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_policies",
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
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "rules",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
            name=op.f("fk_rate_limit_policies_project_id_projects"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rate_limit_policies")),
    )
    op.create_index(
        op.f("ix_rate_limit_policies_project_id"),
        "rate_limit_policies",
        ["project_id"],
        unique=False,
    )

    op.create_table(
        "api_tokens",
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
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("token_prefix", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "project_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rate_limit_policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name=op.f("fk_api_tokens_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["rate_limit_policy_id"],
            ["rate_limit_policies.id"],
            ondelete="SET NULL",
            name=op.f("fk_api_tokens_rate_limit_policy_id_rate_limit_policies"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_tokens")),
        sa.UniqueConstraint("token_prefix", name=op.f("uq_api_tokens_token_prefix")),
    )
    op.create_index(op.f("ix_api_tokens_user_id"), "api_tokens", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_api_tokens_rate_limit_policy_id"),
        "api_tokens",
        ["rate_limit_policy_id"],
        unique=False,
    )

    op.add_column(
        "projects",
        sa.Column("default_rate_limit_policy_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_projects_default_rate_limit_policy_id_rate_limit_policies"),
        "projects",
        "rate_limit_policies",
        ["default_rate_limit_policy_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_projects_default_rate_limit_policy_id"),
        "projects",
        ["default_rate_limit_policy_id"],
        unique=False,
    )

    op.alter_column("rate_limit_policies", "created_at", server_default=None)
    op.alter_column("rate_limit_policies", "updated_at", server_default=None)
    op.alter_column("rate_limit_policies", "enabled", server_default=None)
    op.alter_column("api_tokens", "created_at", server_default=None)
    op.alter_column("api_tokens", "updated_at", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_projects_default_rate_limit_policy_id"), table_name="projects")
    op.drop_constraint(
        op.f("fk_projects_default_rate_limit_policy_id_rate_limit_policies"),
        "projects",
        type_="foreignkey",
    )
    op.drop_column("projects", "default_rate_limit_policy_id")

    op.drop_index(op.f("ix_api_tokens_rate_limit_policy_id"), table_name="api_tokens")
    op.drop_index(op.f("ix_api_tokens_user_id"), table_name="api_tokens")
    op.drop_table("api_tokens")

    op.drop_index(op.f("ix_rate_limit_policies_project_id"), table_name="rate_limit_policies")
    op.drop_table("rate_limit_policies")
