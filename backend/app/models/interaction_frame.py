"""Interaction Frame, Inner Voice Influence, and Advisor Response models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import uuid

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class InteractionFrame(SQLModel, table=True):
    __tablename__ = "interaction_frames"

    frame_id: str = Field(
        default_factory=lambda: f"frm_{uuid.uuid4().hex}",
        primary_key=True,
    )
    user_id: str = Field(foreign_key="users.user_id", index=True)
    identity_instance_id: str = Field(foreign_key="identity_mind_instances.instance_id")
    input_mode: str = Field(default="text", max_length=20)  # text | voice | situation
    # raw_input_ref: reference to encrypted storage location — never raw text in DB
    raw_input_ref: Optional[str] = Field(default=None, max_length=500)
    sanitized_input: Optional[str] = Field(default=None, max_length=15000)
    situation_summary: Optional[str] = Field(default=None, max_length=2000)
    detected_claims: Optional[str] = Field(default=None)  # JSON array
    emotional_state: Optional[str] = Field(default=None, max_length=50)
    residual_novelty_score: float = Field(default=0.0)
    compatibility_score: float = Field(default=0.0)
    strain_score: float = Field(default=0.0)
    closure_score: float = Field(default=0.0)
    leakage_score: float = Field(default=0.0)
    lag_ms: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))


class AdvisorResponse(SQLModel, table=True):
    __tablename__ = "advisor_responses"

    response_id: str = Field(
        default_factory=lambda: f"rsp_{uuid.uuid4().hex}",
        primary_key=True,
    )
    user_id: str = Field(foreign_key="users.user_id", index=True)
    identity_instance_id: str = Field(foreign_key="identity_mind_instances.instance_id")
    interaction_frame_id: str = Field(foreign_key="interaction_frames.frame_id")
    blueprint_version_id: str = Field(foreign_key="core_mind_blueprints.blueprint_id")
    blueprint_checksum: str

    direct_answer: str = Field(max_length=5000)
    what_user_state_suggests: str = Field(max_length=2000)
    what_core_blueprint_corrects: str = Field(max_length=2000)
    reality_check_summary: str = Field(max_length=2000)
    stable_advice: str = Field(max_length=5000)
    best_next_action: str = Field(max_length=1000)
    risks: str = Field(max_length=2000)
    uncertainty: str = Field(max_length=1000)

    confidence_score: float = Field(default=0.0)
    closure_score: float = Field(default=0.0)
    leakage_score: float = Field(default=0.0)
    residual_score: float = Field(default=0.0)
    compatibility_score: float = Field(default=0.0)
    strain_score: float = Field(default=0.0)
    advice_trace_id: str = Field(max_length=100)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
