"""Screen frame and Screen Guardian verdict models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import uuid

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class ScreenFrame(SQLModel, table=True):
    __tablename__ = "screen_frames"

    frame_id: str = Field(
        default_factory=lambda: f"scr_{uuid.uuid4().hex}",
        primary_key=True,
    )
    user_id: str = Field(foreign_key="users.user_id", index=True)
    source_type: str = Field(max_length=30)  # PASTED_TEXT | SCREENSHOT | ...
    extracted_text: Optional[str] = Field(default=None, max_length=20000)
    detected_claims: Optional[str] = Field(default=None)  # JSON
    sensitive_screen_detected: bool = Field(default=False)
    raw_image_stored: bool = Field(default=False)  # always False by default
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))


class ScreenGuardianVerdict(SQLModel, table=True):
    __tablename__ = "screen_guardian_verdicts"

    verdict_id: str = Field(
        default_factory=lambda: f"sgv_{uuid.uuid4().hex}",
        primary_key=True,
    )
    screen_frame_id: str = Field(foreign_key="screen_frames.frame_id")
    claim: str = Field(max_length=2000)
    verdict: str = Field(max_length=30)
    confidence: float = Field(default=0.0)
    reason: str = Field(max_length=2000)
    manipulation_signals: Optional[str] = Field(default=None)  # JSON
    suggested_user_action: Optional[str] = Field(default=None, max_length=500)
    suggested_reply: Optional[str] = Field(default=None, max_length=2000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
