"""Identity Mind Instance model."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import uuid

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class IdentityMindInstance(SQLModel, table=True):
    __tablename__ = "identity_mind_instances"

    instance_id: str = Field(
        default_factory=lambda: f"imi_{uuid.uuid4().hex}",
        primary_key=True,
    )
    user_id: str = Field(foreign_key="users.user_id", index=True, unique=True)
    active_blueprint_version_id: str = Field(
        foreign_key="core_mind_blueprints.blueprint_id"
    )
    stability_band: str = Field(default="STABLE")
    compatibility_with_core: float = Field(default=1.0)
    local_memory_enabled: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))


class UserState(SQLModel, table=True):
    __tablename__ = "user_states"

    state_id: str = Field(
        default_factory=lambda: f"ust_{uuid.uuid4().hex}",
        primary_key=True,
    )
    user_id: str = Field(foreign_key="users.user_id", index=True)
    emotion: Optional[str] = Field(default=None, max_length=50)
    intensity: float = Field(default=0.0)
    pressure: float = Field(default=0.0)
    confusion: float = Field(default=0.0)
    urgency: float = Field(default=0.0)
    fear: float = Field(default=0.0)
    anger: float = Field(default=0.0)
    sadness: float = Field(default=0.0)
    attachment: float = Field(default=0.0)
    goal: Optional[str] = Field(default=None, max_length=500)
    context_summary: Optional[str] = Field(default=None, max_length=2000)
    detected_risks: Optional[str] = Field(default=None)  # JSON
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
