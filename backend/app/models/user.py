"""
User model — core user entity.
user_id is resolved from JWT — NEVER from client-provided claims.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import DateTime
from sqlmodel import Column, Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    user_id: str = Field(
        default_factory=lambda: f"usr_{uuid.uuid4().hex}",
        primary_key=True,
    )
    email: str = Field(unique=True, index=True, max_length=254)
    hashed_password: str
    display_name: Optional[str] = Field(default=None, max_length=100)
    is_active: bool = Field(default=True)
    is_admin: bool = Field(default=False)
    is_verified: bool = Field(default=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    last_login_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
