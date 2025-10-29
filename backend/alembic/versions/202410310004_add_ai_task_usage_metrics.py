"""Add model and token usage columns to ai_tasks

Revision ID: 202410310004
Revises: 202410300003_add_environments_datasets
Create Date: 2024-10-31 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "202410310004"
down_revision = "202410300003_add_environments_datasets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_tasks", sa.Column("model", sa.Text(), nullable=True))
    op.add_column("ai_tasks", sa.Column("prompt_tokens", sa.Integer(), nullable=True))
    op.add_column("ai_tasks", sa.Column("completion_tokens", sa.Integer(), nullable=True))
    op.add_column("ai_tasks", sa.Column("total_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_tasks", "total_tokens")
    op.drop_column("ai_tasks", "completion_tokens")
    op.drop_column("ai_tasks", "prompt_tokens")
    op.drop_column("ai_tasks", "model")
