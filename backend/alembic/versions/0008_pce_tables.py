"""
Migration 0008 — Proficiency-Based Curriculum Engine tables.

Creates:
  learner_profiles
  learner_area_levels
  learner_sessions
"""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learner_profiles",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("user_id", sa.String, nullable=False, unique=True, index=True),
        sa.Column("age", sa.Integer, nullable=False, server_default="0"),
        sa.Column("religion_background", sa.String, nullable=False, server_default="unknown"),
        sa.Column("emotional_condition", sa.Integer, nullable=False, server_default="3"),
        sa.Column("learning_style", sa.String, nullable=False, server_default="mixed"),
        sa.Column("parent_involved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("orientation_notes", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "learner_area_levels",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("user_id", sa.String, nullable=False, index=True),
        sa.Column("area", sa.String, nullable=False, index=True),
        sa.Column("current_level", sa.Integer, nullable=False, server_default="0"),
        sa.Column("session_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sessions_at_level", sa.Integer, nullable=False, server_default="0"),
        sa.Column("avg_engagement", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("last_session_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "area", name="uq_learner_area"),
    )

    op.create_table(
        "learner_sessions",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("user_id", sa.String, nullable=False, index=True),
        sa.Column("area", sa.String, nullable=False, index=True),
        sa.Column("level", sa.Integer, nullable=False, server_default="0"),
        sa.Column("source", sa.String, nullable=False, server_default="both"),
        sa.Column("prompt_used", sa.Text, nullable=False, server_default=""),
        sa.Column("content_summary", sa.Text, nullable=False, server_default=""),
        sa.Column("engagement_score", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("level_up_triggered", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("learner_sessions")
    op.drop_table("learner_area_levels")
    op.drop_table("learner_profiles")
