"""PlatformConnection — OAuth connection from a user to a social platform.

Phase 2+ only. Phase 1 does not use this table.
Access tokens are stored encrypted (application-layer AES-256 before insert).
Never expose raw tokens over the API.

Table: platform_connections
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class PlatformConnection(SQLModel, table=True):
    __tablename__ = "platform_connections"

    id: str = Field(
        default_factory=lambda: f"pc_{uuid.uuid4().hex}",
        primary_key=True,
    )

    # Owner
    user_id: str = Field(index=True, foreign_key="users.user_id")

    # Platform identifier — facebook / instagram / youtube / tiktok / linkedin / x / threads
    platform: str = Field(max_length=50, index=True)

    # Platform-assigned account id
    account_id: str = Field(default="", max_length=200)
    # Human-readable name of the connected page/profile
    account_name: str = Field(default="", max_length=200)

    # Encrypted tokens — use app.security.token_cipher.encrypt/decrypt
    # NEVER return these fields in any API response
    access_token_enc: str = Field(
        default="",
        sa_column=sa.Column(sa.Text, nullable=False, server_default=""),
    )
    refresh_token_enc: str = Field(
        default="",
        sa_column=sa.Column(sa.Text, nullable=False, server_default=""),
    )

    token_expires: Optional[datetime] = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True),
    )

    # JSON list of granted scopes — ["pages_manage_posts", "instagram_basic", ...]
    scope: str = Field(
        default="[]",
        sa_column=sa.Column(sa.Text, nullable=False, server_default="[]"),
    )

    # connected / revoked / expired
    status: str = Field(default="connected", max_length=20, index=True)

    connected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
