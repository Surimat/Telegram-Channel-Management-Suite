"""v2.0 drop the retired promotion-wizard table

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-21 09:00:00.000000

The old promotion wizard was a second onboarding flow that duplicated the single
end-to-end Setup Wizard (D-128: one status system, not two). It was removed along
with its ``promotion_progress`` table. Dropping the table only discards the
wizard's own progress row (a selected preset / last step); no user content,
account or audience data is stored there. The downgrade recreates the table so
the migration is reversible.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("promotion_progress")


def downgrade() -> None:
    op.create_table(
        "promotion_progress",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("preset", sa.String(length=24), nullable=False),
        sa.Column("current_step", sa.String(length=32), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("dismissed", sa.Boolean(), nullable=False),
        sa.Column("completed_steps", sa.Integer(), nullable=False),
        sa.Column("total_steps", sa.Integer(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
