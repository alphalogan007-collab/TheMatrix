"""ScheduledPost — a single platform post queued or published from a ContentPackage.

One ContentPackage can have many ScheduledPosts (one per target platform).
Phase 1: status stays "pending" — user copies/exports manually.
Phase 2: platform API posts to platform and sets platform_post_id.

Table: scheduled_posts
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class ScheduledPost(SQLModel, table=True):
    __tablename__ = "scheduled_posts"

    id: str = Field(
        default_factory=lambda: f"sp_{uuid.uuid4().hex}",
        primary_key=True,
    )

    # Source
    package_id: str = Field(index=True, foreign_key="content_packages.id")
    user_id: str = Field(index=True, foreign_key="users.user_id")

    # Target
    # facebook / instagram / youtube / tiktok / linkedin / x / threads / whatsapp / google_business
    platform: str = Field(max_length=50, index=True)

    # The text/content to be posted (snapshot at time of scheduling)
    content_snapshot: str = Field(
        default="", sa_column=sa.Column(sa.Text, nullable=False, server_default="")
    )

    # Scheduling
    scheduled_for: Optional[datetime] = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True),
    )

    # Set after publish
    published_at: Optional[datetime] = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True),
    )

    # Platform-assigned post id (Phase 2+)
    platform_post_id: str = Field(default="", max_length=200)

    # pending / published / failed / cancelled
    status: str = Field(default="pending", max_length=20, index=True)

    error_message: str = Field(
        default="", sa_column=sa.Column(sa.Text, nullable=False, server_default="")
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
