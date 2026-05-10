"""
Migration 0006 — create seed_conversation_threads and seed_conversation_messages tables.
"""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
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

    op.create_table(
        "seed_conversation_threads",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("mind_name", sa.String, nullable=False, index=True),
        sa.Column("user_id", sa.String, nullable=False, index=True, server_default=""),
        sa.Column("title", sa.String, nullable=False, server_default=""),
        sa.Column("intent", sa.String, nullable=False, server_default=""),
        sa.Column("thread_status", sa.String, nullable=False, server_default="open"),
        sa.Column("message_count", sa.Integer, nullable=False, server_default="0"),
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

    op.create_table(
        "seed_conversation_messages",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("thread_id", sa.String, nullable=False, index=True),
        sa.Column("role", sa.String, nullable=False, server_default="founder"),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("intent_type", sa.String, nullable=False, server_default=""),
        sa.Column("memory_entry_id", sa.String, nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("seed_conversation_messages")
    op.drop_table("seed_conversation_threads")
    op.drop_table("seed_mind_memory_entries")
