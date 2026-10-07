"""v1.8 AI gateway

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-08 12:00:00.000000

Adds the AI Gateway tables: configured providers (``ai_providers``), routing
preferences (``ai_route_settings``) and a bounded observability ring
(``ai_gateway_requests``). The provider API key lives only as a sealed Fernet
token in ``api_key_encrypted``; prompt text, attachments and any secret are never
stored. No browser cookies or third-party session data are stored anywhere.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: str | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'ai_providers',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('provider', sa.String(length=48), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False, server_default='openai_compatible'),
        sa.Column('model', sa.String(length=96), nullable=False, server_default=''),
        sa.Column('base_url', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('api_key_encrypted', sa.Text(), nullable=False, server_default=''),
        sa.Column('auth_mode', sa.String(length=24), nullable=False, server_default='api_key'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cost', sa.String(length=16), nullable=False, server_default='standard'),
        sa.Column('cap_text', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('cap_image', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('cap_file', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('cap_streaming', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('cap_structured', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('cap_verified', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('wrapper_id', sa.String(length=48), nullable=False, server_default=''),
        sa.Column('region_status', sa.String(length=24), nullable=False, server_default=''),
        sa.Column('note', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider'),
    )
    op.create_index('ix_ai_providers_provider', 'ai_providers', ['provider'])

    op.create_table(
        'ai_route_settings',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('key', sa.String(length=48), nullable=False),
        sa.Column('value', sa.Text(), nullable=False, server_default=''),
        sa.Column('value_type', sa.String(length=16), nullable=False, server_default='str'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key'),
    )
    op.create_index('ix_ai_route_settings_key', 'ai_route_settings', ['key'])

    op.create_table(
        'ai_gateway_requests',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('request_id', sa.String(length=48), nullable=False, server_default=''),
        sa.Column('provider', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('model', sa.String(length=96), nullable=False, server_default=''),
        sa.Column('source', sa.String(length=16), nullable=False, server_default=''),
        sa.Column('strategy', sa.String(length=24), nullable=False, server_default=''),
        sa.Column('ok', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('fallback_used', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('latency_ms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=24), nullable=False, server_default=''),
        sa.Column('error_category', sa.String(length=24), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ai_gateway_requests_request_id', 'ai_gateway_requests', ['request_id'])


def downgrade() -> None:
    op.drop_index('ix_ai_gateway_requests_request_id', table_name='ai_gateway_requests')
    op.drop_table('ai_gateway_requests')
    op.drop_index('ix_ai_route_settings_key', table_name='ai_route_settings')
    op.drop_table('ai_route_settings')
    op.drop_index('ix_ai_providers_provider', table_name='ai_providers')
    op.drop_table('ai_providers')
