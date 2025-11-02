"""Add project members table and API uniqueness constraint

Revision ID: 202410280001
Revises: 202310280000
Create Date: 2024-10-28 11:50:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as psql

postgresql = psql

revision: str = "202410280001"
down_revision: str | None = "202310280000"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None

project_role_enum = psql.ENUM(
    "admin",
    "member",
    name="project_role_enum",
    create_type=False,
    schema="public",
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
                WHERE t.typname = 'project_role_enum' AND n.nspname = 'public'
            ) THEN
                CREATE TYPE project_role_enum AS ENUM ('admin', 'member');
            END IF;
        END
        $$;
        """
    )

    op.create_table(
        "project_members",
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
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            project_role_enum,
            nullable=False,
            server_default=sa.text("'member'::project_role_enum"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_project_members_project_id_projects"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_project_members_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_members")),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
    )
    op.create_index(op.f("ix_project_members_project_id"), "project_members", ["project_id"], unique=False)
    op.create_index(op.f("ix_project_members_user_id"), "project_members", ["user_id"], unique=False)

    op.create_unique_constraint(
        "uq_apis_project_method_path_version",
        "apis",
        ["project_id", "method", "path", "version"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_apis_project_method_path_version", "apis", type_="unique")

    op.drop_index(op.f("ix_project_members_user_id"), table_name="project_members")
    op.drop_index(op.f("ix_project_members_project_id"), table_name="project_members")
    op.drop_table("project_members")
    op.execute("DROP TYPE IF EXISTS project_role_enum")
