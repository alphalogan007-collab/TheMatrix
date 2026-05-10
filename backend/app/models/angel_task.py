"""AngelTask — DB model for tasks assigned to Angel Minds.

A task is a discrete piece of work the founder assigns to an angel.
The angel works through it and reports back.

Table: angel_tasks
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


VALID_ANGELS = {
    "gabriel", "michael", "raphael", "azrael", "israfil",
    "kiraman_katibin", "throne", "guardian", "malik",
}

VALID_STATUSES = {"pending", "in_progress", "done", "reported"}


class AngelTask(SQLModel, table=True):
    __tablename__ = "angel_tasks"

    id: str = Field(
        default_factory=lambda: f"at_{uuid.uuid4().hex}",
        primary_key=True,
    )

    # Which angel owns this task
    angel_name: str = Field(index=True)   # "michael", "gabriel", …

    # Task description
    title: str = Field(default="")
    description: str = Field(
        default="",
        sa_column=sa.Column(sa.Text, nullable=False, server_default=""),
    )

    # Domain context (optional — helps the angel focus)
    domain: Optional[str] = Field(default=None)   # e.g. "security", "research", "infra"

    # Priority: low / normal / high / critical
    priority: str = Field(default="normal", index=True)

    # Lifecycle status
    status: str = Field(default="pending", index=True)

    # Outcome written by the angel (or admin) when done
    outcome: Optional[str] = Field(
        default=None,
        sa_column=sa.Column(sa.Text, nullable=True),
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(
            sa.DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    due_at: Optional[datetime] = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True),
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True),
    )

    # Which user assigned the task (always founder/admin in practice)
    assigned_by: Optional[str] = Field(default=None, index=True)
