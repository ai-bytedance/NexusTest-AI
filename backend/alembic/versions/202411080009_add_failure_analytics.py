"""add failure analytics clustering and flakiness columns

Revision ID: 202411080009
Revises: 202411070008
Create Date: 2024-11-08 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202411080009"
down_revision: str | None = "202411070008"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None

cluster_status_enum = postgresql.ENUM(
    "open",
    "muted",
    "resolved",
    name="analytics_fail_cluster_status_enum",
)


def upgrade() -> None:
    bind = op.get_bind()
    cluster_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "analytics_fail_clusters",
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
        sa.Column("signature_hash", sa.String(length=128), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=True),
        sa.Column(
            "sample_report_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', NOW())"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', NOW())"),
        ),
        sa.Column(
            "status",
            cluster_status_enum,
            nullable=False,
            server_default=sa.text("'open'::analytics_fail_cluster_status_enum"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_analytics_fail_clusters_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analytics_fail_clusters")),
    )
    op.create_index(
        op.f("ix_analytics_fail_clusters_project_id"),
        "analytics_fail_clusters",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_analytics_fail_clusters_project_status",
        "analytics_fail_clusters",
        ["project_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_analytics_fail_clusters_last_seen",
        "analytics_fail_clusters",
        ["project_id", "last_seen_at"],
        unique=False,
    )
    op.create_index(
        "ix_analytics_fail_clusters_project_signature",
        "analytics_fail_clusters",
        ["project_id", "signature_hash"],
        unique=True,
    )

    op.add_column(
        "test_reports",
        sa.Column("failure_signature", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "test_reports",
        sa.Column("failure_excerpt", sa.Text(), nullable=True),
    )
    op.add_column(
        "test_reports",
        sa.Column("is_flaky", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
    )
    op.add_column(
        "test_reports",
        sa.Column("flakiness_score", sa.Float(), nullable=True),
    )
    op.create_index(
        "ix_test_reports_failure_signature",
        "test_reports",
        ["project_id", "failure_signature"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_test_reports_failure_signature", table_name="test_reports")
    op.drop_column("test_reports", "flakiness_score")
    op.drop_column("test_reports", "is_flaky")
    op.drop_column("test_reports", "failure_excerpt")
    op.drop_column("test_reports", "failure_signature")

    op.drop_index("ix_analytics_fail_clusters_project_signature", table_name="analytics_fail_clusters")
    op.drop_index("ix_analytics_fail_clusters_last_seen", table_name="analytics_fail_clusters")
    op.drop_index("ix_analytics_fail_clusters_project_status", table_name="analytics_fail_clusters")
    op.drop_index(op.f("ix_analytics_fail_clusters_project_id"), table_name="analytics_fail_clusters")
    op.drop_table("analytics_fail_clusters")

    cluster_status_enum.drop(op.get_bind(), checkfirst=True)
