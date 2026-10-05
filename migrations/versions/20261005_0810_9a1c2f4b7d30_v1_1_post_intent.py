"""v1.1 post intent for reaction narrowing

Revision ID: 9a1c2f4b7d30
Revises: 76d92fe3e70b
Create Date: 2026-10-05 08:10:00.000000

Adds ``posts.intent``: the advisory communicative intent the AI reported for a
post. It narrows which reactions a profile may use (never picks one itself).
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a1c2f4b7d30'
down_revision: str | None = '76d92fe3e70b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('posts', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('intent', sa.String(length=16), nullable=False, server_default='')
        )


def downgrade() -> None:
    with op.batch_alter_table('posts', schema=None) as batch_op:
        batch_op.drop_column('intent')
