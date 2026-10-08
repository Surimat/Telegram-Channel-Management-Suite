"""v1.9 content operations 2.0

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-12 09:00:00.000000

Extends the Content Studio (v1.2) into a single Content Operations pipeline:

* new additive columns on ``content_items`` (AI processing fields + original text)
  and ``publications`` (per-target AI profile, independent comment/delete status);
* three new tables: ``ai_profiles`` (reusable AI profiles), ``automation_rules``
  (declarative SOURCE + CONDITION → ACTION) and ``content_operations``
  (append-only analytics/audit records — metadata only, never secrets).

Every column is additive with a server default, so an existing v1.8 database
upgrades in place. SQLite uses batch mode automatically (render_as_batch).
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- additive columns: content_items -----------------------------------
    with op.batch_alter_table("content_items") as batch:
        batch.add_column(sa.Column("original_text", sa.Text(), nullable=False, server_default=""))
        batch.add_column(
            sa.Column("ai_status", sa.String(length=16), nullable=False, server_default="none")
        )
        batch.add_column(
            sa.Column("ai_category", sa.String(length=32), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column("ai_intent", sa.String(length=32), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column("ai_profile", sa.String(length=64), nullable=False, server_default="")
        )
        batch.add_column(sa.Column("ai_note", sa.Text(), nullable=False, server_default=""))

    # --- additive columns: publications ------------------------------------
    with op.batch_alter_table("publications") as batch:
        batch.add_column(
            sa.Column("profile_key", sa.String(length=64), nullable=False, server_default="")
        )
        batch.add_column(sa.Column("ai_instructions", sa.Text(), nullable=False, server_default=""))
        batch.add_column(
            sa.Column("comment_status", sa.String(length=24), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column("delete_status", sa.String(length=24), nullable=False, server_default="")
        )

    # --- new tables --------------------------------------------------------
    op.create_table(
        "ai_profiles",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("language", sa.String(length=8), nullable=False, server_default="ru"),
        sa.Column("tone", sa.String(length=32), nullable=False, server_default="neutral"),
        sa.Column("max_length", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("system_instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("provider_policy", sa.String(length=32), nullable=False, server_default="auto"),
        sa.Column("actions", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("builtin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_profiles_key", "ai_profiles", ["key"])

    op.create_table(
        "automation_rules",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_kind", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("condition", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("actions", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("profile_key", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_rules_source_kind", "automation_rules", ["source_kind"])

    op.create_table(
        "content_operations",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("publication_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("stage", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("source_kind", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("channel_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("provider", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("model", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_content_operations_item_id", "content_operations", ["item_id"])
    op.create_index(
        "ix_content_operations_publication_id", "content_operations", ["publication_id"]
    )
    op.create_index("ix_content_operations_stage", "content_operations", ["stage"])
    op.create_index("ix_content_operations_status", "content_operations", ["status"])
    op.create_index("ix_content_operations_channel_id", "content_operations", ["channel_id"])


def downgrade() -> None:
    op.drop_table("content_operations")
    op.drop_table("automation_rules")
    op.drop_table("ai_profiles")
    with op.batch_alter_table("publications") as batch:
        batch.drop_column("delete_status")
        batch.drop_column("comment_status")
        batch.drop_column("ai_instructions")
        batch.drop_column("profile_key")
    with op.batch_alter_table("content_items") as batch:
        batch.drop_column("ai_note")
        batch.drop_column("ai_profile")
        batch.drop_column("ai_intent")
        batch.drop_column("ai_category")
        batch.drop_column("ai_status")
        batch.drop_column("original_text")
