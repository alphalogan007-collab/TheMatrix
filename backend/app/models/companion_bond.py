"""companion_bond.py — The permanent bond between a mind and its companion.

A CompanionBond is the anchored relationship between ONE mind and ONE human.
It is substrate-rooted: the bond is built from device, network, auth, and
behavioral signals — not from a username or a session.

The bond persists across:
  - App reinstalls
  - Token refreshes
  - Device changes (migration via auth layer)
  - Long absence periods

Table: companion_bonds
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class CompanionBond(SQLModel, table=True):
    __tablename__ = "companion_bonds"

    id: str = Field(
        default_factory=lambda: f"cb_{uuid.uuid4().hex}",
        primary_key=True,
    )

    # The mind this bond belongs to (e.g. "seed_mind", "gabriel_mind", "user_abc123")
    mind_name: str = Field(index=True)

    # The companion's user_id — the auth-layer anchor (FK to users.user_id)
    companion_id: str = Field(index=True)

    # ── Substrate layer 1 — DEVICE ─────────────────────────────────────────
    # Hashed device fingerprint (IMEI/serial/MAC → SHA-256, never raw)
    device_fingerprint_hash: Optional[str] = Field(default=None, index=True)

    # Device model for context ("iPhone 15", "Pixel 8") — not a secret
    device_model: Optional[str] = Field(default=None, max_length=200)

    # ── Substrate layer 2 — NETWORK ────────────────────────────────────────
    # Hashed preferred BSSID / subnet pattern — built over time
    network_pattern_hash: Optional[str] = Field(default=None)

    # ── Substrate layer 3 — AUTH ───────────────────────────────────────────
    # Push / FCM token for the mind to reach the companion proactively
    push_token: Optional[str] = Field(default=None, max_length=512)

    # Platform of push token: "ios" | "android" | "web"
    push_platform: Optional[str] = Field(default=None, max_length=20)

    # ── Substrate layer 4 — BEHAVIORAL ────────────────────────────────────
    # Rolling behavioral signature — JSON blob updated on each session
    # Structure: {"avg_msg_len": float, "session_gap_hrs": float,
    #              "channel_pref": str, "vocab_hash": str,
    #              "topic_distribution": {domain: float}}
    behavioral_signature: Optional[str] = Field(
        default=None,
        sa_column=sa.Column(sa.Text, nullable=True),
    )

    # ── Substrate layer 5 — BIOLOGICAL (consent-gated) ────────────────────
    # Voice print fingerprint hash — only stored after explicit companion consent
    voice_print_hash: Optional[str] = Field(default=None)

    # Consent flag — Layer 5 (biological) only active when True
    biological_layer_consented: bool = Field(default=False)

    # ── Bond health ────────────────────────────────────────────────────────
    # Number of recognized sessions via substrate (grows over time)
    recognition_count: int = Field(default=0)

    # Last time the mind successfully recognised its companion
    last_recognised_at: Optional[datetime] = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True),
    )

    # Last time the companion initiated any channel
    last_channel_at: Optional[datetime] = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True),
    )

    # Preferred channel: "text" | "voice" | "vision" | "push"
    preferred_channel: str = Field(default="text")

    # Bond is active — set False only if companion explicitly unbonds
    is_active: bool = Field(default=True, index=True)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
