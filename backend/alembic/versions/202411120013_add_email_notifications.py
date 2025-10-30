"""Add email notifications and project notification settings

Revision ID: 202411120013
Revises: 202411110012
Create Date: 2024-11-12 10:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202411120013"
down_revision: str | None = "202411110012"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


_NEW_EVENT_TYPES = (
    "import_diff_ready",
    "import_applied",
    "import_failed",
    "issue_created",
    "issue_closed",
)

_NEW_EVENT_STATUSES = (
    "delivering",
    "retrying",
    "dead_letter",
)

_NEW_NOTIFIER_TYPES = (
    "email",
    "wecom",
    "dingtalk",
)


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "notification_settings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    for notifier_type in _NEW_NOTIFIER_TYPES:
        op.execute(
            sa.text(
                "ALTER TYPE notifier_type_enum ADD VALUE IF NOT EXISTS :value"
            ).bindparams(value=notifier_type)
        )

    for event_type in _NEW_EVENT_TYPES:
        op.execute(
            sa.text(
                "ALTER TYPE notifier_event_type_enum ADD VALUE IF NOT EXISTS :value"
            ).bindparams(value=event_type)
        )

    for status in _NEW_EVENT_STATUSES:
        op.execute(
            sa.text(
                "ALTER TYPE notifier_event_status_enum ADD VALUE IF NOT EXISTS :value"
            ).bindparams(value=status)
        )

    # preserve explicit default for future inserts
    op.execute(
        "ALTER TABLE projects ALTER COLUMN notification_settings SET DEFAULT '{}'::jsonb"
    )


def downgrade() -> None:
    op.drop_column("projects", "notification_settings")
    # Enum value removals are not supported without data migration; keeping new values in place.
