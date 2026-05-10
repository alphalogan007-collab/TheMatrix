"""BrandProfile — per-user content studio brand identity.

Each user can have one brand profile (extensible to many in future).
Stores brand voice, audience, platforms, language preferences, and style notes.

Table: brand_profiles
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class BrandProfile(SQLModel, table=True):
    __tablename__ = "brand_profiles"

    id: str = Field(
        default_factory=lambda: f"bp_{uuid.uuid4().hex}",
        primary_key=True,
    )

    # Owner
    user_id: str = Field(index=True, foreign_key="users.user_id")

    # Core identity
    business_name: str = Field(default="", max_length=200)
    tagline: str = Field(default="", max_length=300)

    # Brand classification
    # warm / professional / playful / inspiring / educational / devotional
    brand_voice: str = Field(default="warm", max_length=50)

    # e.g. "families in Calicut", "Muslim youth", "home bakers"
    primary_audience: str = Field(default="", max_length=300)

    # restaurant / influencer / community / retail / education / NGO / other
    niche: str = Field(default="other", max_length=50)

    # JSON list of strings — ["English", "Malayalam"]
    language_prefs: str = Field(
        default='["English"]',
        sa_column=sa.Column(sa.Text, nullable=False, server_default='["English"]'),
    )

    # JSON list of strings — ["daily engagement", "product sales"]
    posting_goals: str = Field(
        default="[]",
        sa_column=sa.Column(sa.Text, nullable=False, server_default="[]"),
    )

    # Free text — "never use slang, always include Alhamdulillah on milestones"
    style_notes: str = Field(
        default="",
        sa_column=sa.Column(sa.Text, nullable=False, server_default=""),
    )

    # JSON list of active platforms — ["instagram", "facebook", "whatsapp"]
    platform_list: str = Field(
        default="[]",
        sa_column=sa.Column(sa.Text, nullable=False, server_default="[]"),
    )

    # Optional — used in image prompts
    color_palette: str = Field(default="", max_length=200)

    is_active: bool = Field(default=True)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
