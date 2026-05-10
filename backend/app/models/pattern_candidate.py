"""
PatternCandidate — candidate pool for autonomous curriculum expansion.

When the identity engine observes a recurring structural pattern in real
interactions, it records it here BEFORE promoting it to
blueprint_content_entries.

A pattern only becomes permanent curriculum when it has been seen
PROMOTION_THRESHOLD times with mean closure ≥ CLOSURE_FLOOR.  This
prevents noise from polluting the curriculum.

Schema
------
pattern_candidates
  id                TEXT PK
  blueprint_id      TEXT FK
  user_id           TEXT          which user's interactions seeded this
  instance_id       TEXT
  evolution_stage   TEXT          stage at time of observation
  fingerprint       TEXT          structural hash of the pattern (see pattern_observer.py)
  category          TEXT          guidance_direction | moral_constraint | safety_rule
  candidate_text    TEXT          generated description of the pattern
  label             TEXT          short slug for dedup
  observation_count INT           how many times this fingerprint was seen
  mean_closure      FLOAT         rolling mean closure score across observations
  last_closure      FLOAT         closure score on most recent observation
  last_seen_at      TIMESTAMPTZ
  is_promoted       BOOL          True once moved to blueprint_content_entries
  promoted_entry_id TEXT nullable FK to blueprint_content_entries.entry_id
  created_at        TIMESTAMPTZ
  updated_at        TIMESTAMPTZ
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class PatternCandidate(SQLModel, table=True):
    __tablename__ = "pattern_candidates"

    id: str = Field(
        default_factory=lambda: f"pc_{uuid.uuid4().hex}",
        primary_key=True,
    )
    blueprint_id: str = Field(index=True)
    user_id: str = Field(index=True)
    instance_id: str = Field(index=True)

    # Which stage the mind was in when this pattern was first/last observed
    evolution_stage: str = Field(default="NOISE")

    # Structural fingerprint — hash of (basin_state, guidance_mode,
    # emotional_category, stage, closure_bucket).
    # Same fingerprint = same structural pattern.
    fingerprint: str = Field(index=True)

    # Content that will be written to blueprint_content_entries on promotion
    category: str = Field(default="guidance_direction")
    candidate_text: str = Field(sa_column=sa.Column(sa.Text, nullable=False))
    label: str = Field(index=True)          # short slug; used for dedup

    # Observation statistics
    observation_count: int = Field(default=1)
    mean_closure: float = Field(default=0.0)
    last_closure: float = Field(default=0.0)

    # Timestamps
    last_seen_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    is_promoted: bool = Field(default=False)
    promoted_entry_id: Optional[str] = Field(default=None)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
