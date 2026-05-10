"""add_blueprint_content_entries

Revision ID: 0002
Revises: f573c0147ed2
Create Date: 2026-05-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = '0002'
down_revision: str | None = 'f573c0147ed2'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        'blueprint_content_entries',
        sa.Column('entry_id', sa.String(), nullable=False),
        sa.Column('blueprint_id', sa.String(), sa.ForeignKey('core_mind_blueprints.blueprint_id'), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('order_index', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('label', sa.String(), nullable=False, server_default=''),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('entry_id'),
    )
    op.create_index('ix_blueprint_content_entries_blueprint_id', 'blueprint_content_entries', ['blueprint_id'])
    op.create_index('ix_blueprint_content_entries_category', 'blueprint_content_entries', ['category'])


def downgrade() -> None:
    op.drop_index('ix_blueprint_content_entries_category', table_name='blueprint_content_entries')
    op.drop_index('ix_blueprint_content_entries_blueprint_id', table_name='blueprint_content_entries')
    op.drop_table('blueprint_content_entries')
