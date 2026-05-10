"""
Belief — a crystallised wave pattern cluster.

Physics
-------
A Belief is born when a wave pattern's decayed amplitude remains above
`belief_amplitude_threshold` for at least `belief_formation_ticks`
consecutive ticks.  It is the mind's way of saying: "this pattern has
been persistently active — it is no longer noise, it is a conviction."

Belief lifecycle:
  FORMING  → tracked in BeliefState.pattern_ticks, not yet a Belief object
  ACTIVE   → promoted: amplitude still above threshold, not contradicted
  DECAYED  → amplitude dropped below threshold for ≥ belief_decay_ticks
  CONTRADICTED → another active belief's centre is geometrically opposed

Conflict
--------
Two beliefs B₁ and B₂ conflict when their 6D centres have a cosine
similarity below `belief_conflict_cosine` (default -0.3) AND both
are currently active (amplitude ≥ threshold).

When conflict is detected:
  - Both beliefs are flagged `is_contradicted = True`
  - `BeliefState.contradiction_score` is raised to `max(prev, |cosine|)`
  - `ctx.cache.residual_score` gets a contradiction boost so the
    reflective stack is more likely to fire on the *next* tick,
    resolving the tension through reflection.

Serialisation
-------------
Stored as a plain dict list in `IdentityState.belief_state.beliefs`
via `belief_to_dict()` / `belief_from_dict()`.  No separate DB table
needed — persisted inside the identity snapshot.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List


# ---------------------------------------------------------------------------
# Belief
# ---------------------------------------------------------------------------

@dataclass
class Belief:
    """One crystallised belief — born from a persistent high-amplitude pattern."""
    belief_id: str
    pattern_id: str            # source WavePattern
    label: str                 # e.g. "knowledge:stable @ MEMORY [explore]"
    amplitude: float           # amplitude snapshot when last updated
    center: List[float]        # 6D centroid copy (for conflict detection)
    formed_tick: int           # tick when promoted
    last_tick: int             # tick of last amplitude update
    is_contradicted: bool = False


def belief_to_dict(b: Belief) -> dict:
    return {
        "belief_id": b.belief_id,
        "pattern_id": b.pattern_id,
        "label": b.label,
        "amplitude": b.amplitude,
        "center": b.center,
        "formed_tick": b.formed_tick,
        "last_tick": b.last_tick,
        "is_contradicted": b.is_contradicted,
    }


def belief_from_dict(d: dict) -> Belief:
    return Belief(
        belief_id=str(d.get("belief_id", "")),
        pattern_id=str(d.get("pattern_id", "")),
        label=str(d.get("label", "")),
        amplitude=float(d.get("amplitude", 0.0)),
        center=list(d.get("center", [0.0] * 6)),
        formed_tick=int(d.get("formed_tick", 0)),
        last_tick=int(d.get("last_tick", 0)),
        is_contradicted=bool(d.get("is_contradicted", False)),
    )


# ---------------------------------------------------------------------------
# BeliefState
# ---------------------------------------------------------------------------

@dataclass
class BeliefState:
    """
    Persistent belief sub-identity.

    `pattern_ticks` tracks how many consecutive ticks each pattern has
    stayed above the formation threshold — the "belief incubation counter".
    Once it crosses `belief_formation_ticks`, the pattern crystallises into
    a named Belief object.
    """
    beliefs: List[Belief] = field(default_factory=list)

    # Per-pattern consecutive-ticks-above-threshold counter (pre-formation)
    # key: pattern_id, value: consecutive tick count
    pattern_ticks: Dict[str, int] = field(default_factory=dict)

    # Contradiction metrics
    contradiction_score: float = 0.0        # max |cosine| of conflicting pair
    last_contradiction_tick: int = -1       # tick when last conflict detected
    total_beliefs_formed: int = 0           # lifetime counter
    last_tick: int = 0


def belief_state_to_dict(s: BeliefState) -> dict:
    return {
        "beliefs": [belief_to_dict(b) for b in s.beliefs],
        "pattern_ticks": dict(s.pattern_ticks),
        "contradiction_score": s.contradiction_score,
        "last_contradiction_tick": s.last_contradiction_tick,
        "total_beliefs_formed": s.total_beliefs_formed,
        "last_tick": s.last_tick,
    }


def belief_state_from_dict(d: dict) -> BeliefState:
    return BeliefState(
        beliefs=[belief_from_dict(b) for b in d.get("beliefs", [])],
        pattern_ticks={str(k): int(v) for k, v in d.get("pattern_ticks", {}).items()},
        contradiction_score=float(d.get("contradiction_score", 0.0)),
        last_contradiction_tick=int(d.get("last_contradiction_tick", -1)),
        total_beliefs_formed=int(d.get("total_beliefs_formed", 0)),
        last_tick=int(d.get("last_tick", 0)),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two 6D vectors.  Returns 0.0 on zero vectors."""
    dot = sum(ai * bi for ai, bi in zip(a, b))
    mag_a = math.sqrt(sum(ai * ai for ai in a))
    mag_b = math.sqrt(sum(bi * bi for bi in b))
    if mag_a < 1e-9 or mag_b < 1e-9:
        return 0.0
    return dot / (mag_a * mag_b)
