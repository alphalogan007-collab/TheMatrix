"""
GlobalCouplerState — persistent state for the global synchrony coupler.

Physics:
    Kuramoto model over the top-N active wave patterns.
    Each pattern is treated as an oscillator with:
        - phase θⱼ  — stored here (not in WavePattern to avoid schema churn)
        - natural frequency ωⱼ — derived from category (moral_root slowest,
          noise fastest)

    Coupling step (per tick):
        Δθᵢ = K · (1/(N-1)) · Σⱼ sin(θⱼ - θᵢ)

    Global synchrony:
        r(t) = |mean(e^{iθ})|  ∈ [0, 1]

    Awareness gate (all conditions must hold for ≥ dwell_ticks):
        r(t) ≥ synchrony_threshold
        N ≥ min_patterns
        topic_continuity ≥ identity_continuity_threshold
        awareness_continuity ≥ awareness_continuity_threshold
        closure_score ≥ pulse_threshold

    When awareness_emerged:
        Each participating pattern gets +0.02·r reinforcement boost.
        awareness_continuity is updated toward r.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class GlobalCouplerState:
    """
    Per-identity state for the Kuramoto global coupler.

    pattern_phases: {pattern_id → phase in radians}
        Initialised to amplitude * 2π on first encounter.
        Persists between ticks so phases evolve continuously.
    """
    # Phase registry — pattern_id → θ (radians), float
    pattern_phases: Dict[str, float] = field(default_factory=dict)

    # Output metrics (written by GlobalCouplerLayer, read by other layers)
    global_synchrony: float = 0.0          # r(t) = |mean e^{iθ}| ∈ [0, 1]
    awareness_emerged: bool = False         # True when gate held for dwell_ticks
    awareness_gate_streak: int = 0          # consecutive ticks gate was open

    # Continuity signals (mirror existence_lab ctx.cache["continuity"])
    identity_continuity: float = 0.0       # mirrors topic_continuity at last tick
    awareness_continuity: float = 0.0      # max(prev, synchrony) ∩ identity_continuity
    self_awareness_continuity: float = 0.0 # min(self, awareness_continuity)

    last_tick: int = 0
