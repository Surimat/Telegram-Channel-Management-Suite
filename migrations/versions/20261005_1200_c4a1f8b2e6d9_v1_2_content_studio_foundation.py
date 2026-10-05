"""v1.2 content studio foundation

Revision ID: c4a1f8b2e6d9
Revises: b3d7e1a5c9f2
Create Date: 2026-10-05 12:00:00.000000

Creates the Content Studio tables: content sources, items, media assets,
publications, button sets and comment plans (v1.2). All columns are additive and
carry server defaults, so an existing v1.1 database upgrades in place.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4a1f8b2e6d9"
down_revision: str | None = "b3d7e1a5c9f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_sources",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.Enum(
            "TELEGRAM", "RSS", "ATOM", "MANUAL", name="content_source_kind"
        ), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("reference", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("channel_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("account_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("status", sa.Enum(
            "IDLE", "OK", "ERROR", "PROTECTED", name="content_source_status"
        ), nullable=False, server_default="IDLE"),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("etag", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("last_modified", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("last_seen_item", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("last_fetch", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_fetch_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_content_sources_kind", "content_sources", ["kind"])
    op.create_index("ix_content_sources_channel_id", "content_sources", ["channel_id"])

    op.create_table(
        "content_items",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("cleaned_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("entities", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("buttons", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.Enum(
            "IMPORTED", "DRAFT", "READY", "SCHEDULED", "PUBLISHING", "PUBLISHED",
            "FAILED", "ARCHIVED", name="content_item_status",
        ), nullable=False, server_default="IMPORTED"),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("source_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("source_message_id", sa.BigInteger(), nullable=True),
        sa.Column("source_url", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("source_channel", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("source_author", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rights_status", sa.Enum(
            "OWN", "ALLOWED", "LICENSED", "PUBLIC", "UNKNOWN", name="content_rights_status"
        ), nullable=False, server_default="UNKNOWN"),
        sa.Column("attribution_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("protected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("content_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("language", sa.String(length=8), nullable=False, server_default="ru"),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_content_items_status", "content_items", ["status"])
    op.create_index("ix_content_items_source_id", "content_items", ["source_id"])
    op.create_index("ix_content_items_source_hash", "content_items", ["source_hash"])
    op.create_index("ix_content_items_content_hash", "content_items", ["content_hash"])

    op.create_table(
        "media_assets",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="image"),
        sa.Column("filename", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("path", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("mime", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("width", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("height", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration", sa.Float(), nullable=False, server_default="0"),
        sa.Column("media_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("source_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("source_url", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("conversion", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_media_assets_item_id", "media_assets", ["item_id"])
    op.create_index("ix_media_assets_media_hash", "media_assets", ["media_hash"])
    op.create_index("ix_media_assets_source_hash", "media_assets", ["source_hash"])

    op.create_table(
        "publications",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("channel_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("telegram_channel_id", sa.BigInteger(), nullable=True),
        sa.Column("channel_username", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("status", sa.Enum(
            "PLANNED", "SCHEDULED", "PUBLISHING", "PUBLISHED", "FAILED", "CANCELLED",
            name="publication_status",
        ), nullable=False, server_default="PLANNED"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("text_override", sa.Text(), nullable=False, server_default=""),
        sa.Column("media_override", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("buttons_override", sa.Text(), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("telegram_message_ids", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("delete_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_publications_item_id", "publications", ["item_id"])
    op.create_index("ix_publications_channel_id", "publications", ["channel_id"])
    op.create_index("ix_publications_status", "publications", ["status"])
    op.create_index("ix_publications_idempotency_key", "publications", ["idempotency_key"])

    op.create_table(
        "button_sets",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("publication_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("rows", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_button_sets_item_id", "button_sets", ["item_id"])
    op.create_index("ix_button_sets_publication_id", "button_sets", ["publication_id"])

    op.create_table(
        "comment_plans",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("publication_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("item_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("buttons", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("delay_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="planned"),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("discussion_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_comment_plans_publication_id", "comment_plans", ["publication_id"])
    op.create_index("ix_comment_plans_item_id", "comment_plans", ["item_id"])


def downgrade() -> None:
    op.drop_table("comment_plans")
    op.drop_table("button_sets")
    op.drop_table("publications")
    op.drop_table("media_assets")
    op.drop_table("content_items")
    op.drop_table("content_sources")
