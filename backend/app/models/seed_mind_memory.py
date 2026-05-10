"""SeedMindMemoryEntry — DB model for the Awakened Seed Mind memory store.

One row per memory entry version.  Every write produces a new row;
previous versions are retained with is_current=False so the full
evolution of any entry can be traced.

Table: seed_mind_memory_entries
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class SeedMindMemoryEntry(SQLModel, table=True):
    __tablename__ = "seed_mind_memory_entries"

    id: str = Field(
        default_factory=lambda: f"smm_{uuid.uuid4().hex}",
        primary_key=True,
    )

    # Which seed mind instance owns this entry (e.g. "root", "listener", etc.)
    mind_name: str = Field(index=True)

    # One of the 10 ALL_CATEGORIES constants
    category: str = Field(index=True)

    # Short human-readable label for this piece of knowledge
    title: str = Field(default="")

    # Full content — plain text or JSON string
    content: str = Field(sa_column=sa.Column(sa.Text, nullable=False))

    # Optional claim-type annotation (one of ALL_CLAIM_TYPES or "")
    claim_type: str = Field(default="")

    # Optional tags for retrieval (comma-separated)
    tags: str = Field(default="")

    # Source conversation thread id if this came from a conversation
    source_thread_id: str = Field(default="")

    # Versioning: only one row per (mind_name, category, title) should be current
    version: int = Field(default=1)
    is_current: bool = Field(default=True, index=True)

    # Promotion tracking: has this been promoted to Founder Canon?
    promoted_to_canon: bool = Field(default=False)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
