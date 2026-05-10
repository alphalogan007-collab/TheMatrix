"""Initial schema migration — creates all MindAI tables.

Revision ID: 0001
Revises: 
Create Date: 2024-01-01 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Enable extensions (idempotent — run before table creation)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "users",
        sa.Column("user_id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "device_sessions",
        sa.Column("session_id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.user_id"), nullable=False, index=True),
        sa.Column("device_name", sa.String(), nullable=True),
        sa.Column("ip_hash", sa.String(), nullable=True),
        sa.Column("user_agent_hash", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("token_id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("device_sessions.session_id"), nullable=False, index=True),
        sa.Column("token_hash", sa.String(), nullable=False, unique=True),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "user_consents",
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.user_id"), primary_key=True),
        sa.Column("allow_memory", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("allow_screen_guardian", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("allow_voice_processing", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("allow_anonymized_training", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("allow_sensitive_session_storage", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "core_mind_blueprints",
        sa.Column("blueprint_id", sa.String(), primary_key=True),
        sa.Column("version", sa.String(), nullable=False, unique=True),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("checksum", sa.String(), nullable=True),
        sa.Column("signature", sa.String(), nullable=True),
        sa.Column("previous_version_id", sa.String(), nullable=True),
        sa.Column("leakage_tolerance", sa.Float(), nullable=False),
        sa.Column("closure_target", sa.Float(), nullable=False),
        sa.Column("compatibility_threshold", sa.Float(), nullable=False),
        sa.Column("moral_weight", sa.Float(), nullable=False),
        sa.Column("factual_weight", sa.Float(), nullable=False),
        sa.Column("non_harm_weight", sa.Float(), nullable=False),
        sa.Column("reality_weight", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "identity_mind_instances",
        sa.Column("instance_id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.user_id"), nullable=False, unique=True),
        sa.Column("active_blueprint_version_id", sa.String(), sa.ForeignKey("core_mind_blueprints.blueprint_id"), nullable=False),
        sa.Column("stability_band", sa.String(), nullable=False, server_default="STABLE"),
        sa.Column("compatibility_with_core", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("local_memory_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "user_states",
        sa.Column("state_id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.user_id"), nullable=False, index=True),
        sa.Column("emotional_intensity", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("confusion_level", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("pressure_level", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("urgency_level", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("fear_level", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("anger_level", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("sadness_level", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("attachment_level", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "interaction_frames",
        sa.Column("frame_id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.user_id"), nullable=False, index=True),
        sa.Column("raw_input_ref", sa.String(), nullable=True),
        sa.Column("sanitized_input", sa.Text(), nullable=False),
        sa.Column("closure_score", sa.Float(), nullable=True),
        sa.Column("leakage_score", sa.Float(), nullable=True),
        sa.Column("strain_level", sa.String(), nullable=True),
        sa.Column("stability_band", sa.String(), nullable=True),
        sa.Column("blueprint_version", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "advisor_responses",
        sa.Column("response_id", sa.String(), primary_key=True),
        sa.Column("frame_id", sa.String(), sa.ForeignKey("interaction_frames.frame_id"), nullable=False, index=True),
        sa.Column("acknowledgment", sa.Text(), nullable=True),
        sa.Column("identity_reflection", sa.Text(), nullable=True),
        sa.Column("guidance", sa.Text(), nullable=True),
        sa.Column("warning", sa.Text(), nullable=True),
        sa.Column("suggested_action", sa.Text(), nullable=True),
        sa.Column("clarifying_question", sa.Text(), nullable=True),
        sa.Column("safety_note", sa.Text(), nullable=True),
        sa.Column("closure_score", sa.Float(), nullable=True),
        sa.Column("leakage_score", sa.Float(), nullable=True),
        sa.Column("compatibility_score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("blueprint_checksum", sa.String(), nullable=True),
        sa.Column("advice_trace_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "screen_frames",
        sa.Column("frame_id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.user_id"), nullable=False, index=True),
        sa.Column("input_type", sa.String(), nullable=False),
        sa.Column("raw_image_stored", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("text_excerpt", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "screen_guardian_verdicts",
        sa.Column("verdict_id", sa.String(), primary_key=True),
        sa.Column("frame_id", sa.String(), sa.ForeignKey("screen_frames.frame_id"), nullable=False, index=True),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("verdict", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("manipulation_signals", sa.Text(), nullable=True),
        sa.Column("suggested_reply", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "audit_logs",
        sa.Column("log_id", sa.String(), primary_key=True),
        sa.Column("action", sa.String(), nullable=False, index=True),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("actor_user_id", sa.String(), nullable=True, index=True),
        sa.Column("resource_type", sa.String(), nullable=True),
        sa.Column("resource_id", sa.String(), nullable=True),
        sa.Column("ip_hash", sa.String(), nullable=True),
        sa.Column("user_agent_hash", sa.String(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )

    op.create_table(
        "knowledge_patterns",
        sa.Column("pattern_id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.user_id"), nullable=False, index=True),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("text_excerpt", sa.String(), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),  # stored as pgvector via raw SQL
        sa.Column("tags", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "feedback",
        sa.Column("feedback_id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.user_id"), nullable=False, index=True),
        sa.Column("interaction_frame_id", sa.String(), sa.ForeignKey("interaction_frames.frame_id"), nullable=False, index=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("harm_flag", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("has_free_text", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "admin_grants",
        sa.Column("grant_id", sa.String(), primary_key=True),
        sa.Column("granted_to_user_id", sa.String(), sa.ForeignKey("users.user_id"), nullable=False, index=True),
        sa.Column("granted_by_user_id", sa.String(), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("admin_grants")
    op.drop_table("feedback")
    op.drop_table("knowledge_patterns")
    op.drop_table("audit_logs")
    op.drop_table("screen_guardian_verdicts")
    op.drop_table("screen_frames")
    op.drop_table("advisor_responses")
    op.drop_table("interaction_frames")
    op.drop_table("user_states")
    op.drop_table("identity_mind_instances")
    op.drop_table("core_mind_blueprints")
    op.drop_table("user_consents")
    op.drop_table("refresh_tokens")
    op.drop_table("device_sessions")
    op.drop_table("users")
