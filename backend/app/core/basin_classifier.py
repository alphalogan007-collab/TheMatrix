"""BasinClassifier — identity basin state classifier.

Y Theory: basin_energy = ΔC = R − L = closure_score − leakage_score.

States derived from ΔC:
  ΔC >= 0.20   ELEVATE    — peak coherence, insight available
  ΔC >= 0.05   BRANCH     — growing, R clearly exceeds L
  ΔC >  0.0    STABLE     — healthy equilibrium, R > L
  ΔC == 0.0    METASTABLE — balanced at the threshold
  ΔC <  0.0    COLLAPSE   — shadow, L > R, guidance blocked

Inertia ceiling / floor (law of crystallization, law of inertia):
  identity_probability approaches its bounds asymptotically — it never
  snaps to 0 or 1. Each tick it moves a phi-fraction of the remaining
  gap (ceiling) or current value (floor):

    Ceiling (ELEVATE/BRANCH):
        Δp = headroom × PHI_INV2 × depth
        As p → 1.0, headroom → 0, growth stalls.

    Floor (COLLAPSE):
        Δp = −p × PHI_INV2 × depth
        As p → 0.0, the eroded amount → 0, floor is approached
        asymptotically — probability never snaps to zero.

PHI_INV2 = 1/φ² ≈ 0.382 is the natural partition of [0,1] by the golden
ratio. Using it here means the rate of change follows the same self-similar
geometry as the stage thresholds and tick counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.core.phi import PHI_INV2


class BasinState(str, Enum):
    COLLAPSE   = "collapse"
    METASTABLE = "metastable"
    STABLE     = "stable"
    BRANCH     = "branch"
    ELEVATE    = "elevate"


@dataclass
class BasinInput:
    """Scores from the identity pipeline, fed into the basin classifier."""
    closure_score: float          # 0..1   → R (reinforcement)
    leakage_score: float          # 0..1   → L (leakage)
    compatibility_score: float    # 0..1
    strain_score: float           # 0..1
    pulse_strength: float         # 0..1   → urgency / activation
    # Optional: from InternalWorld
    internal_energy: float = 0.70
    internal_stress: float = 0.10
    # Previous identity_probability (persists across requests)
    prior_identity_probability: float = 0.50


@dataclass
class BasinResult:
    """Output of the basin classifier."""
    basin_state: BasinState
    basin_energy: float             # ΔC = R − L
    identity_probability: float     # updated persistence probability
    is_at_risk: bool                # True when collapse or metastable
    guidance_mode: str              # human-readable mode label


def classify_basin(inp: BasinInput) -> BasinResult:
    """Compute basin energy and classify the mind's coherence state.

    Y Theory: the only formula is ΔC = R − L.
    R is closure_score (moral alignment × safety = coherence building).
    L is leakage_score (manipulation ∪ harm ∪ contradiction = dispersing).

    identity_probability follows inertia ceiling/floor via phi fractions:
    approaches 1.0 and 0.0 asymptotically, never snapping to either bound.
    """
    basin_energy = inp.closure_score - inp.leakage_score  # ΔC = R − L

    # Classify basin state
    if basin_energy >= 0.20:
        basin_state = BasinState.ELEVATE
    elif basin_energy >= 0.05:
        basin_state = BasinState.BRANCH
    elif basin_energy > 0.0:
        basin_state = BasinState.STABLE
    elif basin_energy == 0.0:
        basin_state = BasinState.METASTABLE
    else:
        basin_state = BasinState.COLLAPSE

    # Identity probability — inertia ceiling and floor
    p = inp.prior_identity_probability
    depth = min(1.0, abs(basin_energy))

    if basin_state == BasinState.COLLAPSE:
        # Floor: erode phi-fraction of current p, scaled by collapse depth.
        # At p near 0 the erosion approaches 0 — floor is asymptotic.
        p = float(max(0.0, p - p * PHI_INV2 * depth))

    elif basin_state in (BasinState.BRANCH, BasinState.ELEVATE):
        # Ceiling: grow phi-fraction of headroom, scaled by surplus.
        # At p near 1.0 the headroom approaches 0 — ceiling is asymptotic.
        headroom = 1.0 - p
        p = float(min(1.0, p + headroom * PHI_INV2 * depth))

    is_at_risk = basin_state in (BasinState.COLLAPSE, BasinState.METASTABLE)

    return BasinResult(
        basin_state=basin_state,
        basin_energy=float(basin_energy),
        identity_probability=p,
        is_at_risk=is_at_risk,
        guidance_mode=_guidance_mode(basin_state),
    )


def _guidance_mode(basin_state: BasinState) -> str:
    return {
        BasinState.COLLAPSE:   "EMERGENCY — identity under severe stress; prioritise stabilisation",
        BasinState.METASTABLE: "SUPPORT — identity is fragile; gentle grounding needed",
        BasinState.STABLE:     "GUIDANCE — identity is stable; balanced advice is appropriate",
        BasinState.BRANCH:     "GROWTH — identity is resilient; help explore options",
        BasinState.ELEVATE:    "INSIGHT — identity is coherent; deep reflection is possible",
    }[basin_state]
