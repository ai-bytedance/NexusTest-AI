"""Merge webhook v2 and key rotation branches

Revision ID: 202411160102
Revises: 202411130014, 202411150101
Create Date: 2024-11-16 01:02:00.000000
"""

from __future__ import annotations

revision: str = "202411160102"
down_revision: tuple[str, ...] = ("202411130014", "202411150101")
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass