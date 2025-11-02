"""Add dual-valid token rotation and webhook secret cutover

Revision ID: 202411150101
Revises: 202411110012
Create Date: 2024-11-15 01:01:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202411150101"
down_revision: str | None = "202411130014"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    # ApiToken dual-valid rotation fields
    op.add_column("api_tokens", sa.Column("prev_token_hash", sa.String(length=255), nullable=True))
    op.add_column(
        "api_tokens",
        sa.Column("prev_valid_until", sa.DateTime(timezone=True), nullable=True),
    )

    # WebhookSubscription rotation fields
    op.add_column("webhook_subscriptions", sa.Column("pending_secret", sa.String(length=255), nullable=True))
    op.add_column(
        "webhook_subscriptions",
        sa.Column("cutover_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("webhook_subscriptions", "cutover_at")
    op.drop_column("webhook_subscriptions", "pending_secret")
    op.drop_column("api_tokens", "prev_valid_until")
    op.drop_column("api_tokens", "prev_token_hash")
