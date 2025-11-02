"""Initial schema

Revision ID: 202310280000
Revises: 202310270001
Create Date: 2023-10-28 11:07:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as psql

postgresql = psql

revision: str = "202310280000"
down_revision: str | None = "202310270001"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None

user_role_enum = psql.ENUM(
    "admin",
    "member",
    name="user_role_enum",
    create_type=False,
    schema="public",
)
report_entity_type_enum = psql.ENUM(
    "case",
    "suite",
    name="report_entity_type_enum",
    create_type=False,
    schema="public",
)
report_status_enum = psql.ENUM(
    "pending",
    "running",
    "passed",
    "failed",
    "error",
    "skipped",
    name="report_status_enum",
    create_type=False,
    schema="public",
)
ai_task_type_enum = psql.ENUM(
    "generate_cases",
    "generate_assertions",
    "generate_mock",
    "summarize_report",
    name="ai_task_type_enum",
    create_type=False,
    schema="public",
)
ai_task_status_enum = psql.ENUM(
    "pending",
    "success",
    "failed",
    name="ai_task_status_enum",
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
                WHERE t.typname = 'user_role_enum' AND n.nspname = 'public'
            ) THEN
                CREATE TYPE user_role_enum AS ENUM ('admin', 'member');
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
                WHERE t.typname = 'report_entity_type_enum' AND n.nspname = 'public'
            ) THEN
                CREATE TYPE report_entity_type_enum AS ENUM ('case', 'suite');
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
                WHERE t.typname = 'report_status_enum' AND n.nspname = 'public'
            ) THEN
                CREATE TYPE report_status_enum AS ENUM ('pending', 'running', 'passed', 'failed', 'error', 'skipped');
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
                WHERE t.typname = 'ai_task_type_enum' AND n.nspname = 'public'
            ) THEN
                CREATE TYPE ai_task_type_enum AS ENUM ('generate_cases', 'generate_assertions', 'generate_mock', 'summarize_report');
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
                WHERE t.typname = 'ai_task_status_enum' AND n.nspname = 'public'
            ) THEN
                CREATE TYPE ai_task_status_enum AS ENUM ('pending', 'success', 'failed');
            END IF;
        END
        $$;
        """
    )

    op.create_table(
        "users",
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
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            user_role_enum,
            nullable=False,
            server_default=sa.text("'member'::user_role_enum"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )

    op.create_table(
        "projects",
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
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_projects_created_by_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
        sa.UniqueConstraint("name", name=op.f("uq_projects_name")),
        sa.UniqueConstraint("key", name=op.f("uq_projects_key")),
    )
    op.create_index(op.f("ix_projects_created_by"), "projects", ["created_by"], unique=False)

    op.create_table(
        "apis",
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
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False, server_default=sa.text("'v1'")),
        sa.Column("group_name", sa.String(length=255), nullable=True),
        sa.Column("headers", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "mock_example",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_apis_project_id_projects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_apis")),
    )
    op.create_index(op.f("ix_apis_project_id"), "apis", ["project_id"], unique=False)
    op.create_index("ix_apis_headers_gin", "apis", ["headers"], unique=False, postgresql_using="gin")
    op.create_index("ix_apis_params_gin", "apis", ["params"], unique=False, postgresql_using="gin")
    op.create_index("ix_apis_body_gin", "apis", ["body"], unique=False, postgresql_using="gin")
    op.create_index("ix_apis_mock_example_gin", "apis", ["mock_example"], unique=False, postgresql_using="gin")

    op.create_table(
        "test_cases",
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
        sa.Column("api_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("expected", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "assertions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_test_cases_project_id_projects"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["api_id"], ["apis.id"], name=op.f("fk_test_cases_api_id_apis"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_test_cases_created_by_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_test_cases")),
    )
    op.create_index(op.f("ix_test_cases_project_id"), "test_cases", ["project_id"], unique=False)
    op.create_index(op.f("ix_test_cases_api_id"), "test_cases", ["api_id"], unique=False)
    op.create_index(op.f("ix_test_cases_created_by"), "test_cases", ["created_by"], unique=False)
    op.create_index("ix_test_cases_inputs_gin", "test_cases", ["inputs"], unique=False, postgresql_using="gin")
    op.create_index("ix_test_cases_expected_gin", "test_cases", ["expected"], unique=False, postgresql_using="gin")
    op.create_index("ix_test_cases_assertions_gin", "test_cases", ["assertions"], unique=False, postgresql_using="gin")

    op.create_table(
        "test_suites",
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
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "variables",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_test_suites_project_id_projects"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_test_suites_created_by_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_test_suites")),
    )
    op.create_index(op.f("ix_test_suites_project_id"), "test_suites", ["project_id"], unique=False)
    op.create_index(op.f("ix_test_suites_created_by"), "test_suites", ["created_by"], unique=False)
    op.create_index("ix_test_suites_steps_gin", "test_suites", ["steps"], unique=False, postgresql_using="gin")
    op.create_index("ix_test_suites_variables_gin", "test_suites", ["variables"], unique=False, postgresql_using="gin")

    op.create_table(
        "test_reports",
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
        sa.Column("entity_type", report_entity_type_enum, nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            report_status_enum,
            nullable=False,
            server_default=sa.text("'pending'::report_status_enum"),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', NOW())"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column(
            "request_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "response_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "assertions_result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_test_reports_project_id_projects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_test_reports")),
    )
    op.create_index(op.f("ix_test_reports_project_id"), "test_reports", ["project_id"], unique=False)
    op.create_index("ix_test_reports_entity", "test_reports", ["entity_type", "entity_id"], unique=False)
    op.create_index(
        "ix_test_reports_request_payload_gin",
        "test_reports",
        ["request_payload"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_test_reports_response_payload_gin",
        "test_reports",
        ["response_payload"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_test_reports_assertions_result_gin",
        "test_reports",
        ["assertions_result"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_test_reports_metrics_gin",
        "test_reports",
        ["metrics"],
        unique=False,
        postgresql_using="gin",
    )

    op.create_table(
        "ai_tasks",
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
        sa.Column("task_type", ai_task_type_enum, nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column(
            "status",
            ai_task_status_enum,
            nullable=False,
            server_default=sa.text("'pending'::ai_task_status_enum"),
        ),
        sa.Column(
            "input_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "output_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_ai_tasks_project_id_projects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_tasks")),
    )
    op.create_index(op.f("ix_ai_tasks_project_id"), "ai_tasks", ["project_id"], unique=False)
    op.create_index("ix_ai_tasks_input_payload_gin", "ai_tasks", ["input_payload"], unique=False, postgresql_using="gin")
    op.create_index(
        "ix_ai_tasks_output_payload_gin", "ai_tasks", ["output_payload"], unique=False, postgresql_using="gin"
    )


def downgrade() -> None:
    op.drop_index("ix_ai_tasks_output_payload_gin", table_name="ai_tasks")
    op.drop_index("ix_ai_tasks_input_payload_gin", table_name="ai_tasks")
    op.drop_index(op.f("ix_ai_tasks_project_id"), table_name="ai_tasks")
    op.drop_table("ai_tasks")

    op.drop_index("ix_test_reports_metrics_gin", table_name="test_reports")
    op.drop_index("ix_test_reports_assertions_result_gin", table_name="test_reports")
    op.drop_index("ix_test_reports_response_payload_gin", table_name="test_reports")
    op.drop_index("ix_test_reports_request_payload_gin", table_name="test_reports")
    op.drop_index("ix_test_reports_entity", table_name="test_reports")
    op.drop_index(op.f("ix_test_reports_project_id"), table_name="test_reports")
    op.drop_table("test_reports")

    op.drop_index("ix_test_suites_variables_gin", table_name="test_suites")
    op.drop_index("ix_test_suites_steps_gin", table_name="test_suites")
    op.drop_index(op.f("ix_test_suites_created_by"), table_name="test_suites")
    op.drop_index(op.f("ix_test_suites_project_id"), table_name="test_suites")
    op.drop_table("test_suites")

    op.drop_index("ix_test_cases_assertions_gin", table_name="test_cases")
    op.drop_index("ix_test_cases_expected_gin", table_name="test_cases")
    op.drop_index("ix_test_cases_inputs_gin", table_name="test_cases")
    op.drop_index(op.f("ix_test_cases_created_by"), table_name="test_cases")
    op.drop_index(op.f("ix_test_cases_api_id"), table_name="test_cases")
    op.drop_index(op.f("ix_test_cases_project_id"), table_name="test_cases")
    op.drop_table("test_cases")

    op.drop_index("ix_apis_mock_example_gin", table_name="apis")
    op.drop_index("ix_apis_body_gin", table_name="apis")
    op.drop_index("ix_apis_params_gin", table_name="apis")
    op.drop_index("ix_apis_headers_gin", table_name="apis")
    op.drop_index(op.f("ix_apis_project_id"), table_name="apis")
    op.drop_table("apis")

    op.drop_index(op.f("ix_projects_created_by"), table_name="projects")
    op.drop_table("projects")

    op.drop_table("users")

    op.execute("DROP TYPE IF EXISTS ai_task_status_enum")
    op.execute("DROP TYPE IF EXISTS ai_task_type_enum")
    op.execute("DROP TYPE IF EXISTS report_status_enum")
    op.execute("DROP TYPE IF EXISTS report_entity_type_enum")
    op.execute("DROP TYPE IF EXISTS user_role_enum")
