"""Knowledge pattern model — stores embedded knowledge chunks for pgvector retrieval."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlmodel import Column, Field, SQLModel
from pgvector.sqlalchemy import Vector


class KnowledgePattern(SQLModel, table=True):
    __tablename__ = "knowledge_patterns"

    pattern_id: str = Field(
        default_factory=lambda: f"kp_{uuid.uuid4().hex}",
        primary_key=True,
    )
    user_id: str = Field(foreign_key="users.user_id", index=True)
    content_type: str = Field(default="fact")   # fact | belief | goal | context
    source: str = Field(default="user_provided")
    text_excerpt: str = Field(max_length=500)   # truncated reference, not raw PII
    embedding: list[float] | None = Field(default=None, sa_column=Column(Vector(1536)))
    tags: str = Field(default="[]")             # JSON array stored as text
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
