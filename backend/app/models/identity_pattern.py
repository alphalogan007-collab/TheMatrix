"""
IdentityPatternSnapshot — DB model for persisting the full identity pattern.

Each user gets one "current" snapshot row (upserted on every save).
Previous snapshots are kept as backup rows (labelled "checkpoint" or "backup")
so the state can be restored if needed.

Schema:
  identity_pattern_snapshots
    id            TEXT PK
    user_id       TEXT FK → users
    instance_id   TEXT          (identity_mind_instance.instance_id)
    evolution_stage TEXT        (stage name e.g. "MEMORY")
    stage_value   INT           (0-7)
    total_requests INT
    is_trained    BOOL          (stage >= REACTION AND total_requests >= 10)
    snapshot_label TEXT         ("current" | "checkpoint" | "backup")
    state_json    TEXT          (full JSON of IdentityState)
    created_at    TIMESTAMPTZ
    updated_at    TIMESTAMPTZ
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class IdentityPatternSnapshot(SQLModel, table=True):
    __tablename__ = "identity_pattern_snapshots"

    id: str = Field(
        default_factory=lambda: f"ips_{uuid.uuid4().hex}",
        primary_key=True,
    )
    user_id: str = Field(index=True)
    instance_id: str = Field(index=True)

    # Stage summary (denormalised for fast querying without parsing JSON)
    evolution_stage: str = Field(default="NOISE")
    stage_value: int = Field(default=0)
    total_requests: int = Field(default=0)
    is_trained: bool = Field(default=False)

    # Label distinguishes the live row from archived backups
    snapshot_label: str = Field(default="current")   # "current" | "checkpoint" | "backup"

    # Full serialised IdentityState
    state_json: str = Field(sa_column=sa.Column(sa.Text, nullable=False))

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
