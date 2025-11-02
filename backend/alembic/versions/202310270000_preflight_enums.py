"""Preflight reconciliation for PostgreSQL enums.

Revision ID: 202310270000
Revises:
Create Date: 2023-10-27 23:59:59.000000
"""

from __future__ import annotations

from typing import Sequence, Tuple

import sqlalchemy as sa
from alembic import op

revision: str = "202310270000"
down_revision: str | None = None
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None

EnumDefinition = Tuple[str, Tuple[str, ...]]

ENUM_DEFINITIONS: Sequence[EnumDefinition] = (
    ("user_role_enum", ("admin", "member")),
    ("report_entity_type_enum", ("case", "suite")),
    (
        "report_status_enum",
        ("pending", "running", "passed", "failed", "error", "skipped"),
    ),
    (
        "ai_task_type_enum",
        ("generate_cases", "generate_assertions", "generate_mock", "summarize_report"),
    ),
    ("ai_task_status_enum", ("pending", "success", "failed")),
    ("project_role_enum", ("admin", "member")),
    ("execution_plan_type_enum", ("cron", "interval")),
    (
        "notifier_type_enum",
        ("webhook", "feishu", "slack", "email", "wecom", "dingtalk"),
    ),
    (
        "notifier_event_type_enum",
        (
            "run_finished",
            "import_diff_ready",
            "import_applied",
            "import_failed",
            "issue_created",
            "issue_closed",
        ),
    ),
    (
        "notifier_event_status_enum",
        ("pending", "success", "failed", "delivering", "retrying", "dead_letter"),
    ),
    ("dataset_type_enum", ("csv", "excel", "inline")),
    ("org_role_enum", ("owner", "admin", "member")),
    ("team_role_enum", ("owner", "admin", "member")),
    ("identity_provider_enum", ("feishu", "google", "github", "oidc")),
    (
        "analytics_fail_cluster_status_enum",
        ("open", "muted", "resolved"),
    ),
    ("issue_sync_state_enum", ("ok", "error")),
    (
        "integration_webhook_status_enum",
        ("pending", "processing", "processed", "failed"),
    ),
    ("backup_status_enum", ("running", "success", "failed")),
    ("integration_provider_enum", ("jira", "linear", "github")),
    ("issue_link_source_enum", ("manual", "auto")),
    ("webhook_backoff_strategy", ("exponential", "linear", "fixed")),
    ("webhook_delivery_status", ("pending", "delivered", "failed", "dlq")),
    (
        "webhook_event_type",
        (
            "run.started",
            "run.finished",
            "import.diff_ready",
            "import.applied",
            "issue.created",
            "issue.updated",
        ),
    ),
)


def _quote_label(label: str) -> str:
    return "'" + label.replace("'", "''") + "'"


def upgrade() -> None:
    bind = op.get_bind()

    for enum_name, labels in ENUM_DEFINITIONS:
        values_sql = ", ".join(_quote_label(label) for label in labels)
        bind.execute(
            sa.text(
                f"""
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = '{enum_name}'
          AND n.nspname = 'public'
    ) THEN
        CREATE TYPE {enum_name} AS ENUM ({values_sql});
    END IF;
END
$$;
"""
            )
        )

        existing_rows = bind.execute(
            sa.text(
                """
SELECT enumlabel
FROM pg_enum e
JOIN pg_type t ON t.oid = e.enumtypid
JOIN pg_namespace n ON n.oid = t.typnamespace
WHERE t.typname = :enum_name
  AND n.nspname = 'public'
ORDER BY enumsortorder
"""
            ),
            {"enum_name": enum_name},
        )
        existing_labels = [row[0] for row in existing_rows]
        present = set(existing_labels)

        for index, label in enumerate(labels):
            if label in present:
                continue

            before_label = next((later for later in labels[index + 1 :] if later in present), None)
            after_label = next((prev for prev in reversed(labels[:index]) if prev in present), None)

            if before_label is not None:
                bind.execute(
                    sa.text(
                        f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS :value BEFORE :before"
                    ),
                    {"value": label, "before": before_label},
                )
            elif after_label is not None:
                bind.execute(
                    sa.text(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS :value AFTER :after"),
                    {"value": label, "after": after_label},
                )
            else:
                bind.execute(
                    sa.text(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS :value"),
                    {"value": label},
                )

            present.add(label)


def downgrade() -> None:  # pragma: no cover - irreversible preflight migration
    pass
