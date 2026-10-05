"""v1.1 account restriction counter

Revision ID: b3d7e1a5c9f2
Revises: 9a1c2f4b7d30
Create Date: 2026-10-05 09:00:00.000000

Adds ``user_sessions.restriction_count``: how many times Telegram has limited an
account (FloodWait/restriction). It powers the "repeated limits" warning only —
the suite never promises a safe invite count (D-069, account risk UX).
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3d7e1a5c9f2'
down_revision: str | None = '9a1c2f4b7d30'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('restriction_count', sa.Integer(), nullable=False, server_default='0')
        )


def downgrade() -> None:
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.drop_column('restriction_count')
