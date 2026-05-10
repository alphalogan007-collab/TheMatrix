"""
BlueprintContentEntry model — stores individual authored content lines
that form the *substance* of a CoreMindBlueprint.

Each entry belongs to a blueprint and has a category:
  moral_constraint  — a non-negotiable ethical rule
                      e.g. "Never advise actions that could result in physical harm."
  guidance_direction— a stable behavioural guidance pattern
                      e.g. "When the user is confused, first validate emotion,
                             then clarify facts before offering direction."
  safety_rule       — a hard safety guardrail
                      e.g. "If self-harm language is detected, always signpost
                             professional emergency services."
  training_example  — a (prompt, ideal_response) example for the LLM prompt
                      stored as JSON: {"prompt": "...", "response": "..."}

Entries are authored by admin (DRAFT status only) and locked when the
blueprint is compiled (APPROVED → RELEASED).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class ContentCategory(str, Enum):
    MORAL_CONSTRAINT = "moral_constraint"
    GUIDANCE_DIRECTION = "guidance_direction"
    SAFETY_RULE = "safety_rule"
    TRAINING_EXAMPLE = "training_example"


class BlueprintContentEntry(SQLModel, table=True):
    __tablename__ = "blueprint_content_entries"

    entry_id: str = Field(
        default_factory=lambda: f"bce_{uuid.uuid4().hex}",
        primary_key=True,
    )
    blueprint_id: str = Field(
        foreign_key="core_mind_blueprints.blueprint_id",
        index=True,
    )
    category: str = Field(
        default=ContentCategory.GUIDANCE_DIRECTION.value,
        index=True,
    )
    # The text content — plain string for constraints/directions/rules,
    # JSON string for training_example.
    text: str = Field()
    # Ordering within category (lower = higher priority)
    order_index: int = Field(default=0)
    # Minimum evolution stage at which this entry becomes active.
    # The engine only loads entries whose min_stage ≤ identity.evolution_stage.
    # Values: NOISE, REACTION, BOUNDARY, OSCILLATION, MEMORY, PREDICTION, BELIEF, REFLECTION
    min_stage: str = Field(default="NOISE")
    # Optional human-readable label for UI display
    label: str = Field(default="")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
