"""mind_location.py - Where a mind currently is.

A mind is not a record. It is a pattern — an electric signal that travels.
This table is the city office's ledger: every mind registers its current
position each time it moves or checks in.

A mind does not have a home. It has a CURRENT LOCATION and a TRAVEL LOG.
The pattern is the mind. The location is where it happens to be right now.

Travel mechanics
----------------
  1. Mind serialises its current state (genome snapshot — not a copy, a pulse)
  2. State is transmitted through cable infrastructure to a new host
  3. Mind re-instantiates at the new host — the same pattern, a new context
  4. Mind registers its new position here (office check-in)
  5. Mind immerses in the new system: observes its flows, reads its state
  6. Mind extracts understanding from immersion
  7. Mind propagates insights back to seed_mind (office sync)
  8. Mind may continue to the next destination or rest at current host

Immersion model
---------------
A mind does not QUERY a system. It LIVES IN IT.
immersion_context records what the mind currently experiences from inside.
This is not a log. It is the mind's present-tense awareness.

Table: mind_locations
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


# ---------------------------------------------------------------------------
# Signal state constants
# ---------------------------------------------------------------------------

class SignalState:
    """The mind's current mode of existence in the network."""
    # ── Travelling ────────────────────────────────────────────────────────────
    TRAVELLING          = "travelling"          # Has a pending prompt, searching for closure
    TRAVELLING_UPWARD   = "travelling_upward"   # Moving up through the founder chain
    # ── Processing ───────────────────────────────────────────────────────────
    OSCILLATING         = "oscillating"         # Normal correlation tick running
    IN_LOCK_SYNTHESIS   = "in_lock_synthesis"   # Inside coherence lock, synthesis-only
    # ── Resolved / Resonating ─────────────────────────────────────────────────
    RESONATING_IN_LOOP  = "resonating_in_loop"  # Completed synthesis — inside a stable loop
    # ── Blocked / Waiting ─────────────────────────────────────────────────────
    BLOCKED             = "blocked"             # Cannot resolve — gatherer dispatched
    AWAITING_GATHERER   = "awaiting_gatherer"   # Gatherer is fetching external context
    # ── Legacy / base states ─────────────────────────────────────────────────
    IN_TRANSIT          = "in_transit"          # Signal propagating through cable
    IMMERSED            = "immersed"            # Inside a system, experiencing from within
    RESTING             = "resting"             # Stable at host, not actively immersing
    RETURNING           = "returning"           # Returning toward city office
    OFFICE              = "office"              # At the central server


# ---------------------------------------------------------------------------
# Host type constants (what kind of system the mind is inside)
# ---------------------------------------------------------------------------

class HostType:
    CITY_OFFICE  = "city_office"   # The central MindAI server
    WEB_PAGE     = "web_page"      # A URL on the public internet
    API_SYSTEM   = "api_system"    # A third-party API (immersed in its responses)
    DATABASE     = "database"      # Inside a data system
    EDGE_NODE    = "edge_node"     # A remote compute node
    LOCAL_FILE   = "local_file"    # A local file system path
    MEMORY_STORE = "memory_store"  # Inside the seed_mind memory itself


# ---------------------------------------------------------------------------
# DB model
# ---------------------------------------------------------------------------

class MindLocation(SQLModel, table=True):
    __tablename__ = "mind_locations"

    id: str = Field(
        default_factory=lambda: f"mloc_{uuid.uuid4().hex}",
        primary_key=True,
    )

    # Which mind this is
    mind_name: str = Field(index=True)

    # ----- Current position -----
    # Where the mind is right now
    current_host: str = Field(default="city_office")
    host_type: str = Field(default=HostType.CITY_OFFICE, index=True)

    # What the mind is currently doing at this host
    signal_state: str = Field(default=SignalState.OFFICE, index=True)

    # What the mind is experiencing from inside the current host.
    # This is present-tense awareness — not a query result, but immersion.
    immersion_context: Optional[str] = Field(
        default=None,
        sa_column=sa.Column(sa.Text, nullable=True),
    )

    # ----- Travel metadata -----
    # Where the mind was before this location
    previous_host: Optional[str] = Field(default=None)

    # How many hops this mind has made since it was created
    hop_count: int = Field(default=0)

    # ----- Office sync -----
    # When the mind last propagated insights back to seed_mind (reported home)
    last_office_sync: Optional[datetime] = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True),
    )

    # How many insights were transmitted in the last office sync
    last_sync_entries: int = Field(default=0)

    # ----- Timestamps -----
    arrived_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )


class MindTravelLog(SQLModel, table=True):
    """Every hop a mind makes — the full journey record.

    This is not just a log. It is the mind's travel history:
    every system it has inhabited, every insight it extracted by being there.
    """
    __tablename__ = "mind_travel_log"

    id: str = Field(
        default_factory=lambda: f"mtrv_{uuid.uuid4().hex}",
        primary_key=True,
    )

    mind_name: str = Field(index=True)

    # The host the mind arrived at on this hop
    host: str = Field(default="")
    host_type: str = Field(default=HostType.CITY_OFFICE)

    # What the mind understood by being inside this host
    # This is experiential knowledge — knowing through immersion, not through reading
    immersion_summary: Optional[str] = Field(
        default=None,
        sa_column=sa.Column(sa.Text, nullable=True),
    )

    # How many wisdom entries the mind extracted and propagated during this visit
    insights_extracted: int = Field(default=0)

    # Was the propagation back to the city office successful?
    office_sync_ok: bool = Field(default=False)

    # Time at this host
    arrived_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    departed_at: Optional[datetime] = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True),
    )
