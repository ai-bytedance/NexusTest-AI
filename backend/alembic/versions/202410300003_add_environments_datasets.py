"""add environments and datasets"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202410300003"
down_revision: str | None = "202410290002"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None

_UTC_NOW = sa.text("TIMEZONE('utc', NOW())")
_dataset_type_enum = postgresql.ENUM("csv", "excel", "inline", name="dataset_type_enum")


def upgrade() -> None:
    bind = op.get_bind()
    _dataset_type_enum.create(bind, checkfirst=True)

    op.create_table(
        "environments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_UTC_NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_UTC_NOW),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=True),
        sa.Column("headers", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("variables", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("secrets", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_environments_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_environments_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_environments")),
        sa.UniqueConstraint("project_id", "name", name="uq_environments_project_name"),
    )
    op.create_index(op.f("ix_environments_project_id"), "environments", ["project_id"], unique=False)
    op.create_index("ix_environments_headers_gin", "environments", ["headers"], unique=False, postgresql_using="gin")
    op.create_index(
        "ix_environments_variables_gin",
        "environments",
        ["variables"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index("ix_environments_secrets_gin", "environments", ["secrets"], unique=False, postgresql_using="gin")
    op.create_index(
        "uq_environments_project_default",
        "environments",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )

    op.create_table(
        "datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_UTC_NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_UTC_NOW),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", _dataset_type_enum, nullable=False),
        sa.Column("source", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_datasets_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_datasets_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_datasets")),
        sa.UniqueConstraint("project_id", "name", name="uq_datasets_project_name"),
    )
    op.create_index(op.f("ix_datasets_project_id"), "datasets", ["project_id"], unique=False)
    op.create_index("ix_datasets_schema_gin", "datasets", ["schema"], unique=False, postgresql_using="gin")

    op.add_column(
        "test_cases",
        sa.Column("environment_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "test_cases",
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "test_cases",
        sa.Column(
            "param_mapping",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index(op.f("ix_test_cases_environment_id"), "test_cases", ["environment_id"], unique=False)
    op.create_index(op.f("ix_test_cases_dataset_id"), "test_cases", ["dataset_id"], unique=False)
    op.create_index(
        "ix_test_cases_param_mapping_gin",
        "test_cases",
        ["param_mapping"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_foreign_key(
        op.f("fk_test_cases_environment_id_environments"),
        "test_cases",
        "environments",
        ["environment_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_test_cases_dataset_id_datasets"),
        "test_cases",
        "datasets",
        ["dataset_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.alter_column("test_cases", "param_mapping", server_default=None)


def downgrade() -> None:
    op.drop_constraint(op.f("fk_test_cases_dataset_id_datasets"), "test_cases", type_="foreignkey")
    op.drop_constraint(op.f("fk_test_cases_environment_id_environments"), "test_cases", type_="foreignkey")
    op.drop_index("ix_test_cases_param_mapping_gin", table_name="test_cases")
    op.drop_index(op.f("ix_test_cases_dataset_id"), table_name="test_cases")
    op.drop_index(op.f("ix_test_cases_environment_id"), table_name="test_cases")
    op.drop_column("test_cases", "param_mapping")
    op.drop_column("test_cases", "dataset_id")
    op.drop_column("test_cases", "environment_id")

    op.drop_index("ix_datasets_schema_gin", table_name="datasets")
    op.drop_index(op.f("ix_datasets_project_id"), table_name="datasets")
    op.drop_table("datasets")

    op.drop_index("uq_environments_project_default", table_name="environments")
    op.drop_index("ix_environments_secrets_gin", table_name="environments")
    op.drop_index("ix_environments_variables_gin", table_name="environments")
    op.drop_index("ix_environments_headers_gin", table_name="environments")
    op.drop_index(op.f("ix_environments_project_id"), table_name="environments")
    op.drop_table("environments")

    bind = op.get_bind()
    _dataset_type_enum.drop(bind, checkfirst=True)
