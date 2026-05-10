"""
Migration 0004 — create identity_pattern_snapshots table.

This table persists the complete serialised IdentityState per user/instance.
It acts as both the live state store (snapshot_label='current') and an
offline backup archive (snapshot_label='checkpoint' | 'backup').
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "identity_pattern_snapshots",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("user_id", sa.String, nullable=False, index=True),
        sa.Column("instance_id", sa.String, nullable=False, index=True),
        sa.Column("evolution_stage", sa.String, nullable=False, server_default="NOISE"),
        sa.Column("stage_value", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_requests", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_trained", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("snapshot_label", sa.String, nullable=False, server_default="current"),
        sa.Column("state_json", sa.Text, nullable=False),
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
    # Index for fast lookup of current snapshot per user/instance
    op.create_index(
        "ix_identity_pattern_snapshots_user_instance_label",
        "identity_pattern_snapshots",
        ["user_id", "instance_id", "snapshot_label"],
    )


def downgrade() -> None:
    op.drop_index("ix_identity_pattern_snapshots_user_instance_label")
    op.drop_table("identity_pattern_snapshots")
