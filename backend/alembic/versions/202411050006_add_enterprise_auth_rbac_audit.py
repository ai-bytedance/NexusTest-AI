"""add enterprise auth rbac audit foundations

Revision ID: 202411050006
Revises: 202411010005
Create Date: 2024-11-05 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as psql

postgresql = psql

revision: str = "202411050006"
down_revision: str | None = "202411010005"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None

org_role_enum = psql.ENUM(
    "owner",
    "admin",
    "member",
    name="org_role_enum",
    create_type=False,
    schema="public",
)
team_role_enum = psql.ENUM(
    "owner",
    "admin",
    "member",
    name="team_role_enum",
    create_type=False,
    schema="public",
)
identity_provider_enum = psql.ENUM(
    "feishu",
    "google",
    "github",
    "oidc",
    name="identity_provider_enum",
    create_type=False,
    schema="public",
)
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
                WHERE t.typname = 'org_role_enum' AND n.nspname = 'public'
            ) THEN
                CREATE TYPE org_role_enum AS ENUM ('owner', 'admin', 'member');
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
                WHERE t.typname = 'team_role_enum' AND n.nspname = 'public'
            ) THEN
                CREATE TYPE team_role_enum AS ENUM ('owner', 'admin', 'member');
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
                WHERE t.typname = 'identity_provider_enum' AND n.nspname = 'public'
            ) THEN
                CREATE TYPE identity_provider_enum AS ENUM ('feishu', 'google', 'github', 'oidc');
            END IF;
        END
        $$;
        """
    )

    op.create_table(
        "organizations",
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
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "domain_allowlist",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("auto_provision", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_organizations_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
        sa.UniqueConstraint("name", name=op.f("uq_organizations_name")),
        sa.UniqueConstraint("slug", name=op.f("uq_organizations_slug")),
    )
    op.create_index(op.f("ix_organizations_slug"), "organizations", ["slug"], unique=False)
    op.create_index(op.f("ix_organizations_created_by"), "organizations", ["created_by"], unique=False)

    op.create_table(
        "organization_memberships",
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
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            org_role_enum,
            nullable=False,
            server_default=sa.text("'member'::org_role_enum"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_organization_memberships_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_organization_memberships_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_memberships")),
        sa.UniqueConstraint("organization_id", "user_id", name=op.f("uq_organization_memberships_org_user")),
    )
    op.create_index(
        op.f("ix_organization_memberships_organization_id"),
        "organization_memberships",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_memberships_user_id"),
        "organization_memberships",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "teams",
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
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_teams_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teams")),
        sa.UniqueConstraint("organization_id", "slug", name=op.f("uq_teams_org_slug")),
    )
    op.create_index(op.f("ix_teams_organization_id"), "teams", ["organization_id"], unique=False)
    op.create_index(op.f("ix_teams_slug"), "teams", ["slug"], unique=False)

    op.create_table(
        "team_memberships",
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
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            team_role_enum,
            nullable=False,
            server_default=sa.text("'member'::team_role_enum"),
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_team_memberships_team_id_teams"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_team_memberships_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_team_memberships")),
        sa.UniqueConstraint("team_id", "user_id", name=op.f("uq_team_memberships_team_user")),
    )
    op.create_index(op.f("ix_team_memberships_team_id"), "team_memberships", ["team_id"], unique=False)
    op.create_index(op.f("ix_team_memberships_user_id"), "team_memberships", ["user_id"], unique=False)

    op.create_table(
        "project_team_roles",
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
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            project_role_enum,
            nullable=False,
            server_default=sa.text("'member'::project_role_enum"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_team_roles_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_project_team_roles_team_id_teams"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_team_roles")),
        sa.UniqueConstraint("project_id", "team_id", name=op.f("uq_project_team_roles_project_team")),
    )
    op.create_index(op.f("ix_project_team_roles_project_id"), "project_team_roles", ["project_id"], unique=False)
    op.create_index(op.f("ix_project_team_roles_team_id"), "project_team_roles", ["team_id"], unique=False)

    op.create_table(
        "user_identities",
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
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", identity_provider_enum, nullable=False),
        sa.Column("provider_account_id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("access_token", sa.String(length=1024), nullable=True),
        sa.Column("refresh_token", sa.String(length=1024), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_identities_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_identities")),
        sa.UniqueConstraint("provider", "provider_account_id", name=op.f("uq_user_identities_provider_account")),
    )
    op.create_index(op.f("ix_user_identities_user_id"), "user_identities", ["user_id"], unique=False)

    op.create_table(
        "audit_logs",
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
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_audit_logs_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_audit_logs_organization_id_organizations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_audit_logs_project_id_projects"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(op.f("ix_audit_logs_actor_id"), "audit_logs", ["actor_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_project_id"), "audit_logs", ["project_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_organization_id"), "audit_logs", ["organization_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"], unique=False)

    op.add_column(
        "projects",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(op.f("ix_projects_organization_id"), "projects", ["organization_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_projects_organization_id_organizations"),
        "projects",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "users",
        sa.Column(
            "failed_login_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_attempts")

    op.drop_constraint(op.f("fk_projects_organization_id_organizations"), "projects", type_="foreignkey")
    op.drop_index(op.f("ix_projects_organization_id"), table_name="projects")
    op.drop_column("projects", "organization_id")

    op.drop_index(op.f("ix_audit_logs_created_at"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_organization_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_project_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor_id"), table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index(op.f("ix_user_identities_user_id"), table_name="user_identities")
    op.drop_table("user_identities")

    op.drop_index(op.f("ix_project_team_roles_team_id"), table_name="project_team_roles")
    op.drop_index(op.f("ix_project_team_roles_project_id"), table_name="project_team_roles")
    op.drop_table("project_team_roles")

    op.drop_index(op.f("ix_team_memberships_user_id"), table_name="team_memberships")
    op.drop_index(op.f("ix_team_memberships_team_id"), table_name="team_memberships")
    op.drop_table("team_memberships")

    op.drop_index(op.f("ix_teams_slug"), table_name="teams")
    op.drop_index(op.f("ix_teams_organization_id"), table_name="teams")
    op.drop_table("teams")

    op.drop_index(op.f("ix_organization_memberships_user_id"), table_name="organization_memberships")
    op.drop_index(op.f("ix_organization_memberships_organization_id"), table_name="organization_memberships")
    op.drop_table("organization_memberships")

    op.drop_index(op.f("ix_organizations_created_by"), table_name="organizations")
    op.drop_index(op.f("ix_organizations_slug"), table_name="organizations")
    op.drop_table("organizations")

    op.execute("DROP TYPE IF EXISTS identity_provider_enum")
    op.execute("DROP TYPE IF EXISTS team_role_enum")
    op.execute("DROP TYPE IF EXISTS org_role_enum")
