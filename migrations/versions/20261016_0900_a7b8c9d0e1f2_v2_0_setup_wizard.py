"""v2.0 End-to-End Setup Wizard progress

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-16 09:00:00.000000

Adds ``setup_wizard_steps``: the stored, real outcome of each step of the
end-to-end Setup Wizard (D-128). A step is marked verified only after the server
actually ran its check, so the table records the last verification time, result,
human message and how to fix a failure. Only non-secret, display-safe data.
Additive; an existing database upgrades in place.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "setup_wizard_steps",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="unchecked"),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("how_to_fix", sa.Text(), nullable=False, server_default=""),
        sa.Column("channel_id", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_setup_wizard_steps_key", "setup_wizard_steps", ["key"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_setup_wizard_steps_key", table_name="setup_wizard_steps")
    op.drop_table("setup_wizard_steps")
