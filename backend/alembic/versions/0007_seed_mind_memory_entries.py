"""
Migration 0007 — create seed_mind_memory_entries table.
"""

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "seed_mind_memory_entries",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("mind_name", sa.String, nullable=False, index=True),
        sa.Column("category", sa.String, nullable=False, index=True),
        sa.Column("title", sa.String, nullable=False, server_default=""),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("claim_type", sa.String, nullable=False, server_default=""),
        sa.Column("tags", sa.String, nullable=False, server_default=""),
        sa.Column("source_thread_id", sa.String, nullable=False, server_default=""),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default="true", index=True),
        sa.Column("promoted_to_canon", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("seed_mind_memory_entries")
