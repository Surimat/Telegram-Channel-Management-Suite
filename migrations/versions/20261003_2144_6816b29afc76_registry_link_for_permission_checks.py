"""registry link for permission checks

Revision ID: 6816b29afc76
Revises: e3b5890e407e
Create Date: 2026-10-03 21:44:15.309960

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6816b29afc76'
down_revision: str | None = 'e3b5890e407e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('permission_checks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('registry_channel_id', sa.String(length=64), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_permission_checks_registry_channel_id'),
            ['registry_channel_id'],
            unique=False,
        )
    op.execute(
        "UPDATE permission_checks SET registry_channel_id = '' "
        "WHERE registry_channel_id IS NULL"
    )
    with op.batch_alter_table('permission_checks', schema=None) as batch_op:
        batch_op.alter_column(
            'registry_channel_id', existing_type=sa.String(length=64), nullable=False
        )


def downgrade() -> None:
    with op.batch_alter_table('permission_checks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_permission_checks_registry_channel_id'))
        batch_op.drop_column('registry_channel_id')
