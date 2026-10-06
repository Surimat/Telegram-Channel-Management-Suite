"""v1.6 owner auth and config sync

Revision ID: f8b2d3e5a7c9
Revises: e7a1c9d2f4b8
Create Date: 2026-10-07 10:00:00.000000

Creates the Owner Auth identity table (owner_identities) and the Config Sync
state table (config_sync_state). Both are additive and carry server defaults, so
an existing v1.5 database upgrades in place. No Telegram session, TDATA or secret
is stored here: only a one-way PBKDF2 verifier and sealed OAuth tokens.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f8b2d3e5a7c9"
down_revision: str | None = "e7a1c9d2f4b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "owner_identities",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("method", sa.Enum("PASSWORD", "PIN", name="owner_auth_method"),
                  nullable=False, server_default="PASSWORD"),
        sa.Column("verifier", sa.Text(), nullable=False, server_default=""),
        sa.Column("sync_salt", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recovery_hint", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "config_sync_state",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.Enum(
            "NONE", "LOCAL", "GOOGLE_DRIVE", name="sync_provider_kind",
        ), nullable=False, server_default="NONE"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("oauth_token_encrypted", sa.Text(), nullable=False, server_default=""),
        sa.Column("oauth_refresh_encrypted", sa.Text(), nullable=False, server_default=""),
        sa.Column("device_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("device_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("local_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cloud_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cloud_device", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("cloud_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("last_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("config_sync_state")
    op.drop_table("owner_identities")
