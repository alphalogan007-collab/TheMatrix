"""ContentIdea — a rough idea submitted to the content studio inbox.

Represents a single user intent before it is processed into a ContentPackage.
Input types: text, voice (transcribed), image (described), url (scraped).

Table: content_ideas
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class ContentIdea(SQLModel, table=True):
    __tablename__ = "content_ideas"

    id: str = Field(
        default_factory=lambda: f"ci_{uuid.uuid4().hex}",
        primary_key=True,
    )

    # Ownership
    user_id: str = Field(index=True, foreign_key="users.user_id")
    brand_profile_id: Optional[str] = Field(
        default=None, index=True, foreign_key="brand_profiles.id"
    )

    # The raw rough idea exactly as submitted
    raw_input: str = Field(
        sa_column=sa.Column(sa.Text, nullable=False)
    )

    # How it was submitted
    # text / voice / image / url
    input_type: str = Field(default="text", max_length=20)

    # Auto-detected or user-assigned topic label
    detected_topic: str = Field(default="", max_length=200)

    # Workflow state
    # new / generating / ready / scheduled / published / archived
    status: str = Field(default="new", max_length=20, index=True)

    # Which content package was generated from this idea (set after generation)
    package_id: Optional[str] = Field(default=None)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
