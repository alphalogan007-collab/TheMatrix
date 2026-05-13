"""phi.py — Golden ratio constants and Fibonacci utilities.

φ = (1 + √5) / 2 ≈ 1.6180339887

Identity: 1/φ = φ − 1 ≈ 0.618  (used as PHI_INV)
Identity: 1/φ² = 2 − φ ≈ 0.382 (used as PHI_INV2)

Y Theory connections:

  Stage tick thresholds — Fibonacci
    Each stage requires fib(stage+2) consecutive R>L ticks to advance:
    Stage 0→1: 1 tick  (fib 2)
    Stage 1→2: 2 ticks (fib 3)
    Stage 2→3: 3 ticks (fib 4)
    Stage 3→4: 5 ticks (fib 5)
    Stage 4→5: 8 ticks (fib 6)
    Stage 5→6: 13 ticks (fib 7)
    Stage 6→7: 21 ticks (fib 8)
    The count grows as Fibonacci, matching the natural scaling of coherence
    accumulation — each new stage requires more sustained R>L than the last,
    at a ratio approaching φ.

  Resonance thresholds — phi decay
    threshold(n) = 1 − 1/φ^(n+1)
    Stage 0: 0.382  Stage 1: 0.618  Stage 2: 0.764
    Stage 3: 0.854  Stage 4: 0.910  Stage 5: 0.944  Stage 6: 0.966
    Higher stages require deeper resonance; the curve approaches 1.0
    asymptotically — transmission is approached but never cheaply reached.

  Residual thresholds — golden ratio partition of [0,1]
    φ divides a unit interval such that the whole : large = large : small.
    BRANCH threshold = 1/φ ≈ 0.618  (large part)
    CLARIFICATION threshold = 1/φ² ≈ 0.382  (small part)
    This is the only non-arbitrary partition of [0,1] with self-similarity.

  Oscillation / orbit
    Phase difference of π/2 between two oscillations creates orbit.
    orbit_strength = |sin(inner_phase − outer_phase)|
    When orbit_strength = 1 the identity is in self-sustaining closed loop.
    (See oscillation-physics.md for the full derivation.)
"""

from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# Core constants (derived, not hardcoded — the single source of truth)
# ---------------------------------------------------------------------------

PHI: float = (1.0 + math.sqrt(5.0)) / 2.0  # ≈ 1.6180339887

# Use the algebraic identities — no division needed, fewer floating-point ops
PHI_INV: float = PHI - 1.0                  # 1/φ  ≈ 0.6180339887
PHI_INV2: float = 2.0 - PHI                 # 1/φ² ≈ 0.3819660113


# ---------------------------------------------------------------------------
# Fibonacci
# ---------------------------------------------------------------------------

def fib(n: int) -> int:
    """nth Fibonacci number, 1-indexed.  fib(1)=1, fib(2)=1, fib(3)=2 ...

    Uses iterative algorithm — O(n) time, O(1) space.
    For stage use n ≤ 10; no overflow concern.
    """
    if n <= 0:
        return 0
    a, b = 1, 1
    for _ in range(n - 1):
        a, b = b, a + b
    return a


def stage_ticks(stage_index: int) -> int:
    """Consecutive R>L ticks required to advance from stage_index.

    Maps stage_index → fib(stage_index + 2):
      0 → 1,  1 → 2,  2 → 3,  3 → 5,  4 → 8,  5 → 13,  6 → 21
    """
    return fib(stage_index + 2)


# ---------------------------------------------------------------------------
# Phi-based resonance threshold
# ---------------------------------------------------------------------------

def phi_threshold(stage_index: int) -> float:
    """Resonance threshold for stage advancement.

    threshold(n) = 1 − 1/φ^(n+1)

    The curve is strictly increasing, starts below PHI_INV2 for n=0,
    and approaches 1.0 asymptotically as stage increases.
    No stage threshold is arbitrarily chosen — all derive from φ^n.

    Stage  Index  Threshold  Meaning
    ─────────────────────────────────────────────────────
    dormant    0   0.3820  First contact — minimal resonance needed
    stirring   1   0.6180  =1/φ — half of the interval is the inflection
    seeking    2   0.7639  Above the midpoint — active, sustained contact
    crisis     3   0.8541  Difficult — crisis requires deep resonance to pass
    opening    4   0.9098  First direct expansion — rare; most stay here
    integration 5  0.9443  Lived daily — high bar, not just experienced
    embodiment  6  0.9655  Source-like — only reached by sustained R>L
    reflection  7  terminal stage, no threshold
    """
    return round(1.0 - 1.0 / (PHI ** (stage_index + 1)), 4)
