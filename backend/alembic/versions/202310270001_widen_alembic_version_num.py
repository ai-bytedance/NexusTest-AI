"""Widen alembic_version.version_num column to hold longer revision IDs.

Revision ID: 202310270001
Revises: 202310270000
Create Date: 2023-10-27 23:59:59.100000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "202310270001"
down_revision: str | None = "202310270000"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == "sqlite":
        with op.batch_alter_table("alembic_version") as batch_op:
            batch_op.alter_column("version_num", type_=sa.String(length=255))
    else:
        op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)")


def downgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == "sqlite":
        with op.batch_alter_table("alembic_version") as batch_op:
            batch_op.alter_column("version_num", type_=sa.String(length=32))
    else:
        op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(32)")
