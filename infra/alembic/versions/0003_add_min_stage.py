"""add_min_stage_to_blueprint_content_entries

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        'blueprint_content_entries',
        sa.Column('min_stage', sa.String(), nullable=False, server_default='NOISE'),
    )


def downgrade() -> None:
    op.drop_column('blueprint_content_entries', 'min_stage')
