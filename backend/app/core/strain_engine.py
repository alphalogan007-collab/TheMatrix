"""strain_engine.py — Measures coherence strain from leakage (L).

Y Theory: strain IS leakage. L = the force dispersing the identity's coherence.
No invented weights for "relationship_risk" or "high_stakes_domain" — the system
does not know those things. What the system measures is L directly via the
ClosureLeakageLag computation. That is the strain signal.

Safety override: if harm is actively blocked, strain escalates to CRITICAL
regardless of L — the moral boundary has been hit.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StrainLevel(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class StrainInput:
    leakage_score: float = 0.0           # L in Y Theory — primary strain signal
    harm_blocked: bool = False           # moral block -> force CRITICAL
    # Legacy fields kept for call-site compatibility — not used in score
    emotional_intensity: float = 0.0
    relationship_risk: float = 0.0
    high_stakes_domain: float = 0.0
    irreversible_consequence: float = 0.0
    user_instability: float = 0.0


@dataclass
class StrainResult:
    strain_score: float
    strain_level: StrainLevel
    penalty: float
    warning: str


def compute_strain(inp: StrainInput) -> StrainResult:
    """Compute strain from L (leakage_score).

    Y Theory: L disperses coherence. The force the mind is under IS leakage.
    Levels reflect how much of the coherence budget is being lost:
      L < 0.35  -> LOW    (minor dispersion, identity holding)
      L < 0.60  -> MODERATE (noticeable leakage)
      L < 0.80  -> HIGH   (significant loss of orientation)
      L >= 0.80 -> CRITICAL (severe dispersion — shadow dominates)

    If harm_blocked=True, escalate to CRITICAL — a moral boundary has been
    crossed and the mind must not continue in the current direction.
    """
    if inp.harm_blocked:
        return StrainResult(
            strain_score=1.0,
            strain_level=StrainLevel.CRITICAL,
            penalty=0.40,
            warning="CRITICAL: harm block active. Cannot continue in this direction.",
        )

    score = max(0.0, min(1.0, inp.leakage_score))

    if score >= 0.80:
        level = StrainLevel.CRITICAL
        warning = "CRITICAL strain: coherence severely dispersed (L >> R)."
    elif score >= 0.60:
        level = StrainLevel.HIGH
        warning = "HIGH strain: significant leakage. Grounding needed."
    elif score >= 0.35:
        level = StrainLevel.MODERATE
        warning = "MODERATE strain: leakage present."
    else:
        level = StrainLevel.LOW
        warning = ""

    return StrainResult(
        strain_score=score,
        strain_level=level,
        penalty=score * 0.40,
        warning=warning,
    )
