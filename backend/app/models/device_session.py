"""Device session model — tracks active sessions per device."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import uuid

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class DeviceSession(SQLModel, table=True):
    __tablename__ = "device_sessions"

    session_id: str = Field(
        default_factory=lambda: f"ses_{uuid.uuid4().hex}",
        primary_key=True,
    )
    user_id: str = Field(foreign_key="users.user_id", index=True)
    device_name: Optional[str] = Field(default=None, max_length=200)
    device_fingerprint_hash: Optional[str] = None
    ip_hash: Optional[str] = None
    user_agent_hash: Optional[str] = None
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    revoked_at: Optional[datetime] = Field(default=None, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True))


class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_tokens"

    token_id: str = Field(
        default_factory=lambda: f"rt_{uuid.uuid4().hex}",
        primary_key=True,
    )
    user_id: str = Field(foreign_key="users.user_id", index=True)
    session_id: str = Field(foreign_key="device_sessions.session_id")
    token_hash: str = Field(unique=True, index=True)  # store hash, never raw token
    is_revoked: bool = Field(default=False)
    expires_at: datetime = Field(..., sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    used_at: Optional[datetime] = Field(default=None, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True))
