"""Admin model — tracks admin-specific actions and role grants (audit trail)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class AdminGrant(SQLModel, table=True):
    __tablename__ = "admin_grants"

    grant_id: str = Field(
        default_factory=lambda: f"agr_{uuid.uuid4().hex}",
        primary_key=True,
    )
    granted_to_user_id: str = Field(foreign_key="users.user_id", index=True)
    granted_by_user_id: str = Field(foreign_key="users.user_id")
    reason: str = Field(default="")
    is_active: bool = Field(default=True)
    granted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    revoked_at: datetime | None = Field(default=None, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True))
