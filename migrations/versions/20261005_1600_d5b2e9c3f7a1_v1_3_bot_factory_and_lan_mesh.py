"""v1.3 bot factory and LAN mesh

Revision ID: d5b2e9c3f7a1
Revises: c4a1f8b2e6d9
Create Date: 2026-10-05 16:00:00.000000

Creates the Bot Factory tables (bot_batches, bot_candidates) and the LAN Mesh
tables (mesh_nodes, mesh_peers, mesh_pairing_codes, mesh_leases). All columns
are additive and carry server defaults, so an existing v1.2 database upgrades in
place.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d5b2e9c3f7a1"
down_revision: str | None = "c4a1f8b2e6d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Bot Factory ------------------------------------------------------
    op.create_table(
        "bot_batches",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("prefix", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("topic", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("style", sa.String(length=32), nullable=False, server_default="neutral"),
        sa.Column("name_template", sa.String(length=120), nullable=False, server_default="{prefix} {index}"),
        sa.Column("username_template", sa.String(length=120), nullable=False, server_default="{prefix}_{index}_bot"),
        sa.Column("manager_bot_id", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("manager_username", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("account_id", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("channel_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("requested_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.Enum(
            "DRAFT", "CHECKING", "READY", "CREATING", "COMPLETED", "PAUSED",
            "CANCELLED", "FAILED", name="bot_batch_status",
        ), nullable=False, server_default="DRAFT"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bot_batches_status", "bot_batches", ["status"])

    op.create_table(
        "bot_candidates",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("batch_id", sa.String(length=32), nullable=False),
        sa.Column("index", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("suggested_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("suggested_username", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("username_status", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("username_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("creation_status", sa.Enum(
            "GENERATED", "CHECKING", "AVAILABLE", "OCCUPIED", "INVALID", "READY",
            "CREATING", "CREATED", "TOKEN_IMPORTED", "FAILED", "CANCELLED",
            name="bot_candidate_status",
        ), nullable=False, server_default="GENERATED"),
        sa.Column("bot_id", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("telegram_id", sa.Integer(), nullable=True),
        sa.Column("deep_link", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bot_candidates_batch_id", "bot_candidates", ["batch_id"])
    op.create_index("ix_bot_candidates_suggested_username", "bot_candidates", ["suggested_username"])
    op.create_index("ix_bot_candidates_creation_status", "bot_candidates", ["creation_status"])

    # --- LAN Mesh ---------------------------------------------------------
    op.create_table(
        "mesh_nodes",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("version", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("mode", sa.Enum(
            "STANDALONE", "LAN_MESH", "VPS_WORKER", name="mesh_mode"
        ), nullable=False, server_default="STANDALONE"),
        sa.Column("role", sa.Enum(
            "STANDALONE", "COORDINATOR", "WORKER", name="mesh_role"
        ), nullable=False, server_default="STANDALONE"),
        sa.Column("capabilities", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("host", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("port", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coordinator_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id", name="uq_mesh_nodes_node_id"),
    )

    op.create_table(
        "mesh_peers",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("version", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("capabilities", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("host", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("port", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trusted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("credential_hash", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("status", sa.Enum(
            "ONLINE", "OFFLINE", "BUSY", "UNKNOWN", name="mesh_peer_status"
        ), nullable=False, server_default="UNKNOWN"),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mesh_peers_node_id", "mesh_peers", ["node_id"])
    op.create_index("ix_mesh_peers_status", "mesh_peers", ["status"])

    op.create_table(
        "mesh_pairing_codes",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("issued_by", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("used_by", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mesh_pairing_codes_code", "mesh_pairing_codes", ["code"])

    op.create_table(
        "mesh_leases",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("job_id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("requirements", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("lease_owner", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("status", sa.Enum(
            "ACTIVE", "COMPLETED", "EXPIRED", "RELEASED", name="mesh_lease_status"
        ), nullable=False, server_default="ACTIVE"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mesh_leases_job_id", "mesh_leases", ["job_id"])
    op.create_index("ix_mesh_leases_status", "mesh_leases", ["status"])


def downgrade() -> None:
    op.drop_table("mesh_leases")
    op.drop_table("mesh_pairing_codes")
    op.drop_table("mesh_peers")
    op.drop_table("mesh_nodes")
    op.drop_table("bot_candidates")
    op.drop_table("bot_batches")
