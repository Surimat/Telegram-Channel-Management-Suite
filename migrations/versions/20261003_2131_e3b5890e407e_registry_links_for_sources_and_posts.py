"""registry links for sources and posts

Revision ID: e3b5890e407e
Revises: 561f0631d045
Create Date: 2026-10-03 21:31:53.561714

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3b5890e407e'
down_revision: str | None = '561f0631d045'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('audience_sources', schema=None) as batch_op:
        batch_op.add_column(sa.Column('channel_id', sa.String(length=64), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_audience_sources_channel_id'), ['channel_id'], unique=False
        )
    op.execute("UPDATE audience_sources SET channel_id = '' WHERE channel_id IS NULL")
    with op.batch_alter_table('audience_sources', schema=None) as batch_op:
        batch_op.alter_column('channel_id', existing_type=sa.String(length=64), nullable=False)

    with op.batch_alter_table('posts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('registry_channel_id', sa.String(length=64), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_posts_registry_channel_id'), ['registry_channel_id'], unique=False
        )
    op.execute("UPDATE posts SET registry_channel_id = '' WHERE registry_channel_id IS NULL")
    with op.batch_alter_table('posts', schema=None) as batch_op:
        batch_op.alter_column(
            'registry_channel_id', existing_type=sa.String(length=64), nullable=False
        )


def downgrade() -> None:
    with op.batch_alter_table('posts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_posts_registry_channel_id'))
        batch_op.drop_column('registry_channel_id')

    with op.batch_alter_table('audience_sources', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audience_sources_channel_id'))
        batch_op.drop_column('channel_id')
