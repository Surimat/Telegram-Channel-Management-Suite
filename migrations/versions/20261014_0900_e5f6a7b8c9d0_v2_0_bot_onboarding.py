"""v2.0 bot onboarding

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-14 09:00:00.000000

Adds the mass bot-to-channel onboarding queue (v2.0, D-120): a batch connects up
to 50 already-created bots to one channel through Telegram's official
``startchannel`` flow, with a durable, restart-safe queue and a real rights
verification that reuses the existing BindingService.

Two additive tables; an existing v1.9/v2.0 database upgrades in place. SQLite
runs the create in batch mode (render_as_batch).
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bot_onboarding_batches",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("channel_id", sa.String(length=32), nullable=False),
        sa.Column("channel_label", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("rights_profile", sa.String(length=32), nullable=False, server_default="reactions"),
        sa.Column("function", sa.String(length=32), nullable=False, server_default="reactions"),
        sa.Column("requested_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ready_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("permission_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queue_paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bot_onboarding_batches_channel_id",
        "bot_onboarding_batches",
        ["channel_id"],
    )

    op.create_table(
        "bot_onboarding_candidates",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("batch_id", sa.String(length=32), nullable=False),
        sa.Column("index", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("bot_id", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("telegram_id", sa.Integer(), nullable=True),
        sa.Column("bot_username", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("bot_title", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("channel_id", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("rights_profile", sa.String(length=32), nullable=False, server_default="reactions"),
        sa.Column("function", sa.String(length=32), nullable=False, server_default="reactions"),
        sa.Column("deep_link", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("binding_id", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bot_onboarding_candidates_batch_id",
        "bot_onboarding_candidates",
        ["batch_id"],
    )
    op.create_index(
        "ix_bot_onboarding_candidates_bot_id",
        "bot_onboarding_candidates",
        ["bot_id"],
    )
    op.create_index(
        "ix_bot_onboarding_candidates_status",
        "bot_onboarding_candidates",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_bot_onboarding_candidates_status", table_name="bot_onboarding_candidates")
    op.drop_index("ix_bot_onboarding_candidates_bot_id", table_name="bot_onboarding_candidates")
    op.drop_index("ix_bot_onboarding_candidates_batch_id", table_name="bot_onboarding_candidates")
    op.drop_table("bot_onboarding_candidates")
    op.drop_index("ix_bot_onboarding_batches_channel_id", table_name="bot_onboarding_batches")
    op.drop_table("bot_onboarding_batches")