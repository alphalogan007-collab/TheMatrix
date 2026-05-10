"""
Migration 0005 — create pattern_candidates table.

This table is the candidate pool for autonomous curriculum expansion.
Patterns observed during real interactions accumulate here until they
meet the promotion threshold, at which point they are written into
blueprint_content_entries as permanent curriculum.
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pattern_candidates",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("blueprint_id", sa.String, nullable=False, index=True),
        sa.Column("user_id", sa.String, nullable=False, index=True),
        sa.Column("instance_id", sa.String, nullable=False, index=True),
        sa.Column("evolution_stage", sa.String, nullable=False, server_default="NOISE"),
        sa.Column("fingerprint", sa.String, nullable=False, index=True),
        sa.Column("category", sa.String, nullable=False, server_default="guidance_direction"),
        sa.Column("candidate_text", sa.Text, nullable=False),
        sa.Column("label", sa.String, nullable=False, index=True),
        sa.Column("observation_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("mean_closure", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("last_closure", sa.Float, nullable=False, server_default="0.0"),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("is_promoted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("promoted_entry_id", sa.String, nullable=True),
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
    # Unique constraint: one candidate row per (blueprint, fingerprint)
    op.create_index(
        "ix_pattern_candidates_blueprint_fingerprint",
        "pattern_candidates",
        ["blueprint_id", "fingerprint"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_pattern_candidates_blueprint_fingerprint")
    op.drop_table("pattern_candidates")
