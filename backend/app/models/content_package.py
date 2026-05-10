"""ContentPackage — AI-generated multi-platform content package.

One package corresponds to one ContentIdea.
All 14 platform outputs are stored as individual columns so they can be
patched/regenerated independently without overwriting the whole row.

Table: content_packages
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class ContentPackage(SQLModel, table=True):
    __tablename__ = "content_packages"

    id: str = Field(
        default_factory=lambda: f"cp_{uuid.uuid4().hex}",
        primary_key=True,
    )

    # Source
    idea_id: str = Field(index=True, foreign_key="content_ideas.id")
    user_id: str = Field(index=True, foreign_key="users.user_id")
    brand_profile_id: Optional[str] = Field(default=None)

    # ── Text outputs ─────────────────────────────────────────────────────────
    facebook_post: str = Field(
        default="", sa_column=sa.Column(sa.Text, nullable=False, server_default="")
    )
    instagram_caption: str = Field(
        default="", sa_column=sa.Column(sa.Text, nullable=False, server_default="")
    )
    linkedin_post: str = Field(
        default="", sa_column=sa.Column(sa.Text, nullable=False, server_default="")
    )
    x_post: str = Field(
        default="", sa_column=sa.Column(sa.Text, nullable=False, server_default="")
    )
    threads_post: str = Field(
        default="", sa_column=sa.Column(sa.Text, nullable=False, server_default="")
    )
    whatsapp_status: str = Field(
        default="", sa_column=sa.Column(sa.Text, nullable=False, server_default="")
    )
    google_business_post: str = Field(
        default="", sa_column=sa.Column(sa.Text, nullable=False, server_default="")
    )

    # ── Structured script outputs (stored as JSON strings) ──────────────────
    # {hook, scenes:[{action,voiceover,on_screen_text}], cta, caption, thumbnail_text, duration}
    reel_script: str = Field(
        default="{}", sa_column=sa.Column(sa.Text, nullable=False, server_default="{}")
    )
    # Same structure, TikTok pacing
    tiktok_script: str = Field(
        default="{}", sa_column=sa.Column(sa.Text, nullable=False, server_default="{}")
    )
    # {hook, scenes, cta, title_options, thumbnail_text, duration}
    youtube_shorts_script: str = Field(
        default="{}", sa_column=sa.Column(sa.Text, nullable=False, server_default="{}")
    )

    # ── Supporting assets ────────────────────────────────────────────────────
    # JSON list of hashtag strings
    hashtags: str = Field(
        default="[]", sa_column=sa.Column(sa.Text, nullable=False, server_default="[]")
    )
    cta: str = Field(default="", max_length=500)
    image_prompt: str = Field(
        default="", sa_column=sa.Column(sa.Text, nullable=False, server_default="")
    )
    video_prompt: str = Field(
        default="", sa_column=sa.Column(sa.Text, nullable=False, server_default="")
    )
    alt_text: str = Field(default="", max_length=500)

    # JSON: {language: str, posts: {platform: text}} — secondary language package
    regional_version: str = Field(
        default="{}", sa_column=sa.Column(sa.Text, nullable=False, server_default="{}")
    )

    # Metadata
    # which AI model / prompt version generated this
    model_version: str = Field(default="", max_length=100)

    # Workflow state: draft / ready / archived
    status: str = Field(default="draft", max_length=20, index=True)

    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
