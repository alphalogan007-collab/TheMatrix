"""
closure_leakage_lag.py — Closure / Leakage / Lag computation for the engine.

Closure score  — how much the current response is grounded / sealed / coherent.
Leakage score  — how much unprocessed risk or ambiguity bleeds through.
Lag            — how long the system took to respond (affects trust in the answer).

Used by ClosureStrainLayer to write:
  ctx.cache.closure_score
  ctx.cache.leakage_score
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClosureLeakageLagInput:
    # Closure drivers (higher = more closed / grounded)
    evidence_score: float = 0.0          # factual backing present
    source_agreement: float = 0.0        # sources agree with each other
    moral_alignment: float = 1.0         # moral kernel approved
    non_harm_score: float = 1.0          # no harm detected (0 = harmed blocked)
    long_term_stability: float = 0.70    # answer is stable under future scrutiny

    # Leakage drivers (higher = more leakage / risk bleeding through)
    contradiction_score: float = 0.0     # internal contradictions detected
    missing_context_score: float = 0.0   # key context is absent
    manipulation_score: float = 0.0      # manipulation signals in input
    emotional_overpressure: float = 0.0  # user urgency / stress pushing the answer
    harm_risk: float = 0.0               # residual harm risk

    # Lag
    lag_ms: float = 0.0                  # response latency in milliseconds


@dataclass
class ClosureLeakageLagResult:
    closure_score: float    # 0–1, higher = well-grounded
    leakage_score: float    # 0–1, higher = more risk bleeding through
    lag_penalty: float      # 0–1, higher = latency is causing trust loss
    is_leaking: bool        # True when leakage_score > threshold
    note: str


_CLOSURE_WEIGHTS = {
    "evidence_score":       0.25,
    "source_agreement":     0.20,
    "moral_alignment":      0.25,
    "non_harm_score":       0.20,
    "long_term_stability":  0.10,
}

_LEAKAGE_WEIGHTS = {
    "contradiction_score":     0.20,
    "missing_context_score":   0.20,
    "manipulation_score":      0.25,
    "emotional_overpressure":  0.15,
    "harm_risk":               0.20,
}

_LEAKAGE_THRESHOLD = 0.40   # above this = is_leaking = True
_LAG_HIGH_MS       = 3000   # ms beyond which full lag penalty applies


def compute_closure_leakage_lag(inp: ClosureLeakageLagInput) -> ClosureLeakageLagResult:
    """Compute closure, leakage, and lag penalty scores from the input signals."""

    closure = (
        inp.evidence_score       * _CLOSURE_WEIGHTS["evidence_score"]
        + inp.source_agreement   * _CLOSURE_WEIGHTS["source_agreement"]
        + inp.moral_alignment    * _CLOSURE_WEIGHTS["moral_alignment"]
        + inp.non_harm_score     * _CLOSURE_WEIGHTS["non_harm_score"]
        + inp.long_term_stability* _CLOSURE_WEIGHTS["long_term_stability"]
    )
    closure = max(0.0, min(1.0, closure))

    leakage = (
        inp.contradiction_score    * _LEAKAGE_WEIGHTS["contradiction_score"]
        + inp.missing_context_score* _LEAKAGE_WEIGHTS["missing_context_score"]
        + inp.manipulation_score   * _LEAKAGE_WEIGHTS["manipulation_score"]
        + inp.emotional_overpressure * _LEAKAGE_WEIGHTS["emotional_overpressure"]
        + inp.harm_risk            * _LEAKAGE_WEIGHTS["harm_risk"]
    )
    leakage = max(0.0, min(1.0, leakage))

    # Lag penalty: linear 0→_LAG_HIGH_MS, capped at 1.0
    lag_penalty = min(1.0, inp.lag_ms / _LAG_HIGH_MS) if inp.lag_ms > 0 else 0.0

    # High lag slightly inflates leakage (slow answers carry more uncertainty)
    leakage = min(1.0, leakage + lag_penalty * 0.10)

    is_leaking = leakage > _LEAKAGE_THRESHOLD

    if closure >= 0.75 and not is_leaking:
        note = "Well-grounded. Answer is closed and stable."
    elif is_leaking and closure < 0.50:
        note = "High leakage, low closure. Response carries unresolved risk — apply caution."
    elif is_leaking:
        note = "Partial leakage detected. Closure is adequate but risk persists."
    else:
        note = "Moderate closure. Acceptable for current context."

    return ClosureLeakageLagResult(
        closure_score=closure,
        leakage_score=leakage,
        lag_penalty=lag_penalty,
        is_leaking=is_leaking,
        note=note,
    )
