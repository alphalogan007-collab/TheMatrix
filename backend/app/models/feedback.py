"""Feedback model — stores thumbs up/down on advisor responses."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class Feedback(SQLModel, table=True):
    __tablename__ = "feedback"

    feedback_id: str = Field(
        default_factory=lambda: f"fbk_{uuid.uuid4().hex}",
        primary_key=True,
    )
    user_id: str = Field(foreign_key="users.user_id", index=True)
    interaction_frame_id: str = Field(foreign_key="interaction_frames.frame_id", index=True)
    rating: int = Field()                          # 1 or -1
    harm_flag: bool = Field(default=False)
    has_free_text: bool = Field(default=False)     # presence only, not content (privacy)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
