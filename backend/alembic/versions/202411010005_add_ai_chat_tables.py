"""add ai chat tables

Revision ID: 202411010005
Revises: 202410310004
Create Date: 2024-11-01 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

_revision = "202411010005"

# revision identifiers, used by Alembic.
revision = _revision
down_revision = "202410310004"
branch_labels = None
depends_on = None

_UTC_NOW = sa.text("TIMEZONE('utc', NOW())")


def upgrade() -> None:
    op.create_table(
        "ai_chats",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_UTC_NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_UTC_NOW),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_ai_chats_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_ai_chats_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_chats")),
    )
    op.create_index(op.f("ix_ai_chats_project_id"), "ai_chats", ["project_id"], unique=False)
    op.create_index(op.f("ix_ai_chats_created_by"), "ai_chats", ["created_by"], unique=False)

    op.create_table(
        "ai_chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_UTC_NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_UTC_NOW),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("tool_invoked", sa.String(length=64), nullable=True),
        sa.Column("result_ref", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["ai_chats.id"],
            name=op.f("fk_ai_chat_messages_chat_id_ai_chats"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_ai_chat_messages_author_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_chat_messages")),
        sa.UniqueConstraint("chat_id", "sequence", name="uq_ai_chat_messages_chat_seq"),
    )
    op.create_index(op.f("ix_ai_chat_messages_chat_id"), "ai_chat_messages", ["chat_id"], unique=False)
    op.create_index(op.f("ix_ai_chat_messages_author_id"), "ai_chat_messages", ["author_id"], unique=False)
    op.create_index(op.f("ix_ai_chat_messages_sequence"), "ai_chat_messages", ["sequence"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ai_chat_messages_sequence"), table_name="ai_chat_messages")
    op.drop_index(op.f("ix_ai_chat_messages_author_id"), table_name="ai_chat_messages")
    op.drop_index(op.f("ix_ai_chat_messages_chat_id"), table_name="ai_chat_messages")
    op.drop_table("ai_chat_messages")

    op.drop_index(op.f("ix_ai_chats_created_by"), table_name="ai_chats")
    op.drop_index(op.f("ix_ai_chats_project_id"), table_name="ai_chats")
    op.drop_table("ai_chats")
