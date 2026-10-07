"""v1.7 bot factory creation queue

Revision ID: a1b2c3d4e5f6
Revises: f8b2d3e5a7c9
Create Date: 2026-10-08 09:00:00.000000

Turns the Bot Factory batch into a durable creation *queue* (D-109): each
candidate gains a granular ``queue_state`` (``pending`` → ``queued`` →
``running`` → ``success``/``failed``, plus ``skipped``/``cancelled``) and an
``attempts`` counter, and the batch gains ``skipped_count`` and
``queue_cancelled``. The state is stored as a plain string on purpose: a SQLite
CHECK constraint cannot be extended by an ALTER.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = 'f8b2d3e5a7c9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('bot_batches', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('skipped_count', sa.Integer(), nullable=False, server_default='0')
        )
        batch_op.add_column(
            sa.Column('queue_cancelled', sa.Boolean(), nullable=False, server_default=sa.false())
        )

    with op.batch_alter_table('bot_candidates', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'queue_state', sa.String(length=16), nullable=False, server_default='pending'
            )
        )
        batch_op.add_column(
            sa.Column('attempts', sa.Integer(), nullable=False, server_default='0')
        )
        batch_op.add_column(
            sa.Column('token_mask', sa.String(length=32), nullable=False, server_default='')
        )
    op.create_index(
        'ix_bot_candidates_queue_state', 'bot_candidates', ['queue_state']
    )


def downgrade() -> None:
    op.drop_index('ix_bot_candidates_queue_state', table_name='bot_candidates')
    with op.batch_alter_table('bot_candidates', schema=None) as batch_op:
        batch_op.drop_column('token_mask')
        batch_op.drop_column('attempts')
        batch_op.drop_column('queue_state')
    with op.batch_alter_table('bot_batches', schema=None) as batch_op:
        batch_op.drop_column('queue_cancelled')
        batch_op.drop_column('skipped_count')
