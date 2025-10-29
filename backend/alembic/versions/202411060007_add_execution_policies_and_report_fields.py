"""add execution policies and report fields

Revision ID: 202411060007
Revises: 202411050006
Create Date: 2024-11-06 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202411060007"
down_revision: str | None = "202411050006"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "execution_policies",
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
        sa.Column("max_concurrency", sa.Integer(), nullable=True),
        sa.Column("per_host_qps", sa.Float(), nullable=True),
        sa.Column(
            "retry_max_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("3"),
        ),
        sa.Column(
            "retry_backoff",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "timeout_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("30"),
        ),
        sa.Column(
            "circuit_breaker_threshold",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("5"),
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
            name=op.f("fk_execution_policies_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_execution_policies")),
        sa.UniqueConstraint(
            "project_id",
            "name",
            name=op.f("uq_execution_policies_project_name"),
        ),
    )
    op.create_index(op.f("ix_execution_policies_project_id"), "execution_policies", ["project_id"], unique=False)
    op.create_index(
        "ix_execution_policies_project_enabled",
        "execution_policies",
        ["project_id", "enabled"],
        unique=False,
    )

    op.add_column(
        "projects",
        sa.Column("default_policy_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        op.f("ix_projects_default_policy_id"),
        "projects",
        ["default_policy_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_projects_default_policy_id_execution_policies"),
        "projects",
        "execution_policies",
        ["default_policy_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "test_reports",
        sa.Column("parent_report_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "test_reports",
        sa.Column(
            "run_number",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column(
        "test_reports",
        sa.Column(
            "retry_attempt",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "test_reports",
        sa.Column(
            "policy_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_foreign_key(
        op.f("fk_test_reports_parent_report_id_test_reports"),
        "test_reports",
        "test_reports",
        ["parent_report_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_test_reports_parent_report_id",
        "test_reports",
        ["parent_report_id"],
        unique=False,
    )
    op.create_index(
        "ix_test_reports_entity_run_number",
        "test_reports",
        ["project_id", "entity_type", "entity_id", "run_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_test_reports_entity_run_number", table_name="test_reports")
    op.drop_index("ix_test_reports_parent_report_id", table_name="test_reports")
    op.drop_constraint(
        op.f("fk_test_reports_parent_report_id_test_reports"),
        "test_reports",
        type_="foreignkey",
    )
    op.drop_column("test_reports", "policy_snapshot")
    op.drop_column("test_reports", "retry_attempt")
    op.drop_column("test_reports", "run_number")
    op.drop_column("test_reports", "parent_report_id")

    op.drop_constraint(
        op.f("fk_projects_default_policy_id_execution_policies"),
        "projects",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_projects_default_policy_id"), table_name="projects")
    op.drop_column("projects", "default_policy_id")

    op.drop_index("ix_execution_policies_project_enabled", table_name="execution_policies")
    op.drop_index(op.f("ix_execution_policies_project_id"), table_name="execution_policies")
    op.drop_table("execution_policies")
