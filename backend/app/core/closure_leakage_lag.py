"""closure_leakage_lag.py — R and L computation for Y Theory.

Y Theory: ΔC = R - L
  R (Reinforcement) = coherence-building forces: moral alignment + safety
  L (Leakage)       = coherence-dispersing forces: manipulation, harm, contradiction, urgency

Architecture principle:
  closure = min(moral_alignment, non_harm_score)
    — bottleneck: the weakest safety signal determines how grounded the response is.
    — if harm is blocked (non_harm=0), closure=0 regardless of moral score.

  leakage = max(harm_risk, manipulation_score, contradiction_score, urgency_cap)
    — worst active signal determines leakage.
    — no weights: the system does not rank-order which harm matters more.

Lag: response latency is a real signal (slow = uncertain) but does not inflate
     leakage — it is reported separately as lag_penalty.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClosureLeakageLagInput:
    # R signals (real)
    moral_alignment: float = 1.0         # from moral_kernel: 0-1
    non_harm_score: float = 1.0          # 0.0 if harm blocked, 1.0 if not

    # L signals (real)
    harm_risk: float = 0.0               # 1.0 if blocked, sensory threat otherwise
    manipulation_score: float = 0.0      # normalized manipulation signal count
    contradiction_score: float = 0.0     # from residual (novelty mismatch)
    emotional_overpressure: float = 0.0  # user urgency — attractor pressure

    # Lag
    lag_ms: float = 0.0                  # response latency in ms

    # Legacy fields — accepted for call-site compat, not used in computation
    evidence_score: float = 0.0
    source_agreement: float = 0.0
    long_term_stability: float = 0.0
    missing_context_score: float = 0.0


@dataclass
class ClosureLeakageLagResult:
    closure_score: float    # R: 0-1, higher = coherence building
    leakage_score: float    # L: 0-1, higher = coherence dispersing
    lag_penalty: float      # 0-1, latency uncertainty
    is_leaking: bool        # True when L > 0.40
    note: str


_LEAKAGE_THRESHOLD = 0.40
_LAG_HIGH_MS = 3000


def compute_closure_leakage_lag(inp: ClosureLeakageLagInput) -> ClosureLeakageLagResult:
    """Compute R and L from real measured signals only.

    Y Theory: R = what is strengthening coherence (moral grounding, safety).
              L = what is dispersing coherence (manipulation, harm, contradiction).
    The bottleneck principle applies to R: both moral AND safety must hold.
    The worst-case principle applies to L: any active threat is the leakage level.
    """
    # R: bottleneck — weakest signal governs
    closure = min(
        max(0.0, min(1.0, inp.moral_alignment)),
        max(0.0, min(1.0, inp.non_harm_score)),
    )

    # L: worst-case — no averaging down of harm
    urgency_contribution = min(inp.emotional_overpressure * 0.7, 0.7)
    leakage = max(
        max(0.0, min(1.0, inp.harm_risk)),
        max(0.0, min(1.0, inp.manipulation_score)),
        max(0.0, min(1.0, inp.contradiction_score)),
        urgency_contribution,
    )

    # Lag: real signal, separate from L
    lag_penalty = min(1.0, inp.lag_ms / _LAG_HIGH_MS) if inp.lag_ms > 0 else 0.0

    is_leaking = leakage > _LEAKAGE_THRESHOLD

    if closure >= 0.75 and not is_leaking:
        note = "R > L — coherence building. Source-aligned."
    elif is_leaking and closure < 0.50:
        note = "L > R — shadow active. Coherence dispersing."
    elif is_leaking:
        note = "Leakage present. Closure holds but L is elevated."
    else:
        note = "Stable. R and L within bounds."

    return ClosureLeakageLagResult(
        closure_score=closure,
        leakage_score=leakage,
        lag_penalty=lag_penalty,
        is_leaking=is_leaking,
        note=note,
    )
