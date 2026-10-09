"""v2.0 target language

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-13 09:00:00.000000

Adds the Target Language stage to the Content Studio (v2.0): an explicit
source/target language per source, per item, per channel and per publication, so
a post can be translated only when the languages actually differ. Every column is
additive with a server default, so an existing v1.9 database upgrades in place.
SQLite uses batch mode automatically (render_as_batch).
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- content_sources: source/target language ---------------------------
    with op.batch_alter_table("content_sources") as batch:
        batch.add_column(
            sa.Column("source_language", sa.String(length=8), nullable=False, server_default="auto")
        )
        batch.add_column(
            sa.Column("target_language", sa.String(length=8), nullable=False, server_default="auto")
        )
        batch.add_column(
            sa.Column("auto_detect", sa.Boolean(), nullable=False, server_default=sa.true())
        )

    # --- content_items: detected source + resolved target -------------------
    with op.batch_alter_table("content_items") as batch:
        batch.add_column(
            sa.Column("source_language", sa.String(length=8), nullable=False, server_default="auto")
        )
        batch.add_column(
            sa.Column("target_language", sa.String(length=8), nullable=False, server_default="")
        )

    # --- publications: per-target language override -------------------------
    with op.batch_alter_table("publications") as batch:
        batch.add_column(
            sa.Column("target_language", sa.String(length=8), nullable=False, server_default="")
        )

    # --- channels: channel-level target language ---------------------------
    with op.batch_alter_table("channels") as batch:
        batch.add_column(
            sa.Column("target_language", sa.String(length=8), nullable=False, server_default="auto")
        )


def downgrade() -> None:
    with op.batch_alter_table("channels") as batch:
        batch.drop_column("target_language")
    with op.batch_alter_table("publications") as batch:
        batch.drop_column("target_language")
    with op.batch_alter_table("content_items") as batch:
        batch.drop_column("target_language")
        batch.drop_column("source_language")
    with op.batch_alter_table("content_sources") as batch:
        batch.drop_column("auto_detect")
        batch.drop_column("target_language")
        batch.drop_column("source_language")
