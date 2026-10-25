"""v2.0 invite rolling rate-limit report

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-15 09:00:00.000000

Adds ``invite_jobs.rate_limited_at``: when a bulk run was paused because a
personal account hit the rolling 24-hour invite ceiling (``invite_max_per_day``).
It is a display-only honest report (D-006/D-123) — the scheduler reads the real
invite history from the tasks, so this column only lets the UI say *when* the run
may continue. Additive; an existing database upgrades in place.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("invite_jobs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("rate_limited_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("invite_jobs", schema=None) as batch_op:
        batch_op.drop_column("rate_limited_at")
