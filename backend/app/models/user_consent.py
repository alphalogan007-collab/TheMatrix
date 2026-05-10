"""User consent model — privacy-protective defaults."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class UserConsent(SQLModel, table=True):
    __tablename__ = "user_consents"

    user_id: str = Field(
        foreign_key="users.user_id",
        primary_key=True,
    )
    # All defaults are privacy-protective (False = opt-in required)
    allow_memory: bool = Field(default=False)
    allow_screen_guardian: bool = Field(default=False)
    allow_voice_processing: bool = Field(default=False)
    allow_anonymized_training: bool = Field(default=False)
    allow_sensitive_session_storage: bool = Field(default=False)
    updated_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True),
    )
