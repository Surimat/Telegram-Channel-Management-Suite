"""v1.4 notification center and editorial workspace

Revision ID: e7a1c9d2f4b8
Revises: d5b2e9c3f7a1
Create Date: 2026-10-06 10:00:00.000000

Creates the Notification Center tables (notifications, notification_deliveries)
and the Editorial Workspace tables (editorial_rooms, editorial_members,
editorial_items, editorial_audit). All columns are additive and carry server
defaults, so an existing v1.3 database upgrades in place.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e7a1c9d2f4b8"
down_revision: str | None = "d5b2e9c3f7a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Notification Center ---------------------------------------------
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False, server_default="system"),
        sa.Column("priority", sa.Enum(
            "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL",
            name="notification_priority",
        ), nullable=False, server_default="INFO"),
        sa.Column("destination", sa.Enum(
            "TELEGRAM_OWNER", "TELEGRAM_GROUP", "WINDOWS_TOAST", "NONE",
            name="notification_destination",
        ), nullable=False, server_default="TELEGRAM_OWNER"),
        sa.Column("event_key", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("dedup_key", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("source_module", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("how_to_fix", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.Enum(
            "PENDING", "SENT", "FAILED", "SKIPPED", "POSTPONED", "AGGREGATED",
            name="notification_status",
        ), nullable=False, server_default="PENDING"),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("aggregate_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("postponed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_category", "notifications", ["category"])
    op.create_index("ix_notifications_priority", "notifications", ["priority"])
    op.create_index("ix_notifications_event_key", "notifications", ["event_key"])
    op.create_index("ix_notifications_dedup_key", "notifications", ["dedup_key"])
    op.create_index("ix_notifications_status", "notifications", ["status"])

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("notification_id", sa.String(length=32), nullable=False),
        sa.Column("destination", sa.Enum(
            "TELEGRAM_OWNER", "TELEGRAM_GROUP", "WINDOWS_TOAST", "NONE",
            name="notification_destination",
        ), nullable=False, server_default="TELEGRAM_OWNER"),
        sa.Column("status", sa.Enum(
            "PENDING", "SENT", "FAILED", "SKIPPED", "POSTPONED", "AGGREGATED",
            name="notification_status",
        ), nullable=False, server_default="PENDING"),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notification_deliveries_notification_id",
        "notification_deliveries",
        ["notification_id"],
    )

    # --- Editorial Workspace ---------------------------------------------
    op.create_table(
        "editorial_rooms",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("channel_id", sa.String(length=32), nullable=False),
        sa.Column("channel_label", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("bot_id", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("group_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("group_title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("status", sa.Enum(
            "NOT_CONNECTED", "NEEDS_RIGHTS", "READY", "ERROR",
            name="editorial_room_status",
        ), nullable=False, server_default="NOT_CONNECTED"),
        sa.Column("topics", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("bot_is_member", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("bot_is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_send_messages", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_edit_messages", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_delete_messages", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_manage_topics", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_checked", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_id", name="uq_editorial_room_channel"),
    )
    op.create_index("ix_editorial_rooms_channel_id", "editorial_rooms", ["channel_id"])
    op.create_index("ix_editorial_rooms_status", "editorial_rooms", ["status"])
    op.create_index("ix_editorial_rooms_group_chat_id", "editorial_rooms", ["group_chat_id"])

    op.create_table(
        "editorial_members",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("room_id", sa.String(length=32), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("username", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("role", sa.Enum(
            "OWNER", "EDITOR", "MODERATOR", "VIEWER", name="editorial_role"
        ), nullable=False, server_default="VIEWER"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "telegram_user_id", name="uq_editorial_member"),
    )
    op.create_index("ix_editorial_members_room_id", "editorial_members", ["room_id"])
    op.create_index("ix_editorial_members_telegram_user_id", "editorial_members", ["telegram_user_id"])

    op.create_table(
        "editorial_items",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("room_id", sa.String(length=32), nullable=False),
        sa.Column("content_item_id", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("channel_id", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("channel_label", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("status", sa.Enum(
            "INBOX", "EDITING", "REVIEW", "APPROVED", "SCHEDULED", "PUBLISHED",
            "REJECTED", "PAUSED", "FAILED", name="editorial_status",
        ), nullable=False, server_default="INBOX"),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("topic_id", sa.BigInteger(), nullable=True),
        sa.Column("card_message_id", sa.BigInteger(), nullable=True),
        sa.Column("published_message_id", sa.BigInteger(), nullable=True),
        sa.Column("assigned_user_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("title", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "room_id", "content_item_id", "channel_id", name="uq_editorial_item_target"
        ),
    )
    op.create_index("ix_editorial_items_room_id", "editorial_items", ["room_id"])
    op.create_index("ix_editorial_items_content_item_id", "editorial_items", ["content_item_id"])
    op.create_index("ix_editorial_items_channel_id", "editorial_items", ["channel_id"])
    op.create_index("ix_editorial_items_status", "editorial_items", ["status"])
    op.create_index("ix_editorial_items_order_index", "editorial_items", ["order_index"])
    op.create_index("ix_editorial_items_room_status", "editorial_items", ["room_id", "status"])

    op.create_table(
        "editorial_audit",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("room_id", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("item_id", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("actor_telegram_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("actor_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("action", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("old_status", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("new_status", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_editorial_audit_room_id", "editorial_audit", ["room_id"])
    op.create_index("ix_editorial_audit_item_id", "editorial_audit", ["item_id"])


def downgrade() -> None:
    op.drop_table("editorial_audit")
    op.drop_table("editorial_items")
    op.drop_table("editorial_members")
    op.drop_table("editorial_rooms")
    op.drop_table("notification_deliveries")
    op.drop_table("notifications")
