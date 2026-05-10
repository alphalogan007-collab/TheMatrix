"""
CoreMindBlueprint model — database-level storage of blueprint versions.
Released versions are immutable: no UPDATE permitted via normal API.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import uuid

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from app.core.core_mind_blueprint import BlueprintStatus


class CoreMindBlueprintRecord(SQLModel, table=True):
    __tablename__ = "core_mind_blueprints"

    blueprint_id: str = Field(
        default_factory=lambda: f"bp_{uuid.uuid4().hex}",
        primary_key=True,
    )
    version: str = Field(unique=True, index=True, max_length=50)
    checksum: str                          # SHA-256
    signature: str                         # HMAC/RSA signature
    moral_kernel_version: str = Field(max_length=50)
    fact_kernel_version: str = Field(max_length=50)
    guidance_kernel_version: str = Field(max_length=50)
    safety_kernel_version: str = Field(max_length=50)
    training_dataset_refs: str = Field(default="[]")  # JSON array of hashes
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True),
    )
    released_at: Optional[datetime] = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True),
    )
    changelog: str = Field(default="")
    is_active: bool = Field(default=False)
    status: str = Field(default=BlueprintStatus.DRAFT.value, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    # previous_version_id enables version chain for rollback
    previous_version_id: Optional[str] = Field(
        default=None, foreign_key="core_mind_blueprints.blueprint_id"
    )

    # ── Authoring fields (from initial migration 0001) ───────────────────────
    description: str = Field(default="")
    leakage_tolerance: float = Field(default=0.35)
    closure_target: float = Field(default=0.80)
    compatibility_threshold: float = Field(default=0.60)
    moral_weight: float = Field(default=0.35)
    factual_weight: float = Field(default=0.25)
    non_harm_weight: float = Field(default=0.25)
    reality_weight: float = Field(default=0.15)
