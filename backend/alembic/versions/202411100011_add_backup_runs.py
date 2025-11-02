"""add backup runs table

Revision ID: 202411100011
Revises: 202411090010
Create Date: 2024-11-10 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202411100011"
down_revision: str | None = "202411090010"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None

backup_status_enum = sa.Enum("running", "success", "failed", name="backup_status_enum", create_type=False)


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_type t
                JOIN pg_namespace n ON n.oid = t.typnamespace
                WHERE t.typname = 'backup_status_enum' AND n.nspname = 'public'
            ) THEN
                CREATE TYPE backup_status_enum AS ENUM ('running', 'success', 'failed');
            END IF;
        END
        $$;
        """
    )

    op.create_table(
        "backup_runs",
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
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', NOW())"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            backup_status_enum,
            nullable=False,
            server_default=sa.text("'running'::backup_status_enum"),
        ),
        sa.Column(
            "storage_targets",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'local'"),
        ),
        sa.Column("location", sa.String(length=1024), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column(
            "retention_class",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'daily'"),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("triggered_by", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verify_notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_backup_runs")),
    )
    op.create_index(op.f("ix_backup_runs_started_at"), "backup_runs", ["started_at"], unique=False)

    op.alter_column("backup_runs", "status", server_default=None)
    op.alter_column("backup_runs", "retention_class", server_default=None)
    op.alter_column("backup_runs", "storage_targets", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_backup_runs_started_at"), table_name="backup_runs")
    op.drop_table("backup_runs")
    op.execute("DROP TYPE IF EXISTS backup_status_enum")
