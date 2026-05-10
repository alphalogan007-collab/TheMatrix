"""seed_conversation.py — DB model for founder ↔ seed-mind conversation threads.

Two tables:
  seed_conversation_threads  — one row per conversation session
  seed_conversation_messages — one row per message within a thread
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class SeedConversationThread(SQLModel, table=True):
    __tablename__ = "seed_conversation_threads"

    id: str = Field(
        default_factory=lambda: f"sct_{uuid.uuid4().hex}",
        primary_key=True,
    )

    # Which seed mind this conversation is with
    mind_name: str = Field(index=True)

    # User / founder who owns this thread
    user_id: str = Field(index=True, default="")

    # Short summary title, auto-set from first message
    title: str = Field(default="")

    # Dominant intent of the thread (teaching / questioning / correction / exploration / reflection / instruction)
    intent: str = Field(default="")

    # Thread status: open | paused | ready_for_archive | archived
    thread_status: str = Field(default="open")

    # Number of messages in thread (maintained for quick display)
    message_count: int = Field(default=0)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )


class SeedConversationMessage(SQLModel, table=True):
    __tablename__ = "seed_conversation_messages"

    id: str = Field(
        default_factory=lambda: f"scm_{uuid.uuid4().hex}",
        primary_key=True,
    )

    thread_id: str = Field(index=True)

    # "founder" or "mind"
    role: str = Field(default="founder")

    # The message text
    content: str = Field(sa_column=sa.Column(sa.Text, nullable=False))

    # Classified intent of this message
    intent_type: str = Field(default="")

    # If this message triggered a memory write, the entry id is stored here
    memory_entry_id: str = Field(default="")

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
