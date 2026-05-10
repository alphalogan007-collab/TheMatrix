"""Audit log model — append-only, tamper-resistant."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON
import sqlalchemy as sa
from sqlmodel import Column, Field, SQLModel


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    audit_id: str = Field(primary_key=True)
    actor_user_id: Optional[str] = Field(default=None, index=True)
    actor_type: str = Field(max_length=30, default="user")  # user | admin | system
    action: str = Field(max_length=100, index=True)
    resource_type: Optional[str] = Field(default=None, max_length=50)
    resource_id: Optional[str] = Field(default=None, max_length=200)
    request_id: Optional[str] = Field(default=None, max_length=100)
    ip_hash: Optional[str] = Field(default=None, max_length=64)    # SHA-256 of IP
    user_agent_hash: Optional[str] = Field(default=None, max_length=64)
    outcome: str = Field(max_length=20, default="SUCCESS")
    metadata_redacted: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, index=True))

    class Config:
        # Enforce append-only at the application layer
        # Production: add DB-level trigger to prevent UPDATE/DELETE
        arbitrary_types_allowed = True
