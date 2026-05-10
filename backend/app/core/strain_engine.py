"""
Strain Engine — Measures how much a proposed response may damage
the user's situation, relationships, identity, safety, or future stability.

High strain → pause, reduce confidence, recommend safer path.
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
    emotional_intensity: float = 0.0     # user's current emotional charge (0–1)
    relationship_risk: float = 0.0       # advice may damage important relationships
    high_stakes_domain: float = 0.0      # medical/legal/financial/self-harm domain flag
    irreversible_consequence: float = 0.0  # action cannot be undone
    user_instability: float = 0.0        # user's current stability state


@dataclass
class StrainResult:
    strain_score: float
    strain_level: StrainLevel
    penalty: float                      # applied as negative in advice_stability_score
    warning: str


def compute_strain(inp: StrainInput) -> StrainResult:
    """
    Compute strain for a proposed advice direction.

    Components are weighted to reflect real-world stakes:
    - Irreversible consequences and high-stakes domains get highest weight
    - Emotional intensity modulates but does not dominate
    """
    score = min(
        1.0,
        (
            inp.emotional_intensity * 0.15
            + inp.relationship_risk * 0.20
            + inp.high_stakes_domain * 0.25
            + inp.irreversible_consequence * 0.25
            + inp.user_instability * 0.15
        ),
    )

    if score >= 0.80:
        level = StrainLevel.CRITICAL
        warning = (
            "CRITICAL strain: this advice direction carries high risk of irreversible harm. "
            "Recommend professional support and safe next step only."
        )
    elif score >= 0.60:
        level = StrainLevel.HIGH
        warning = (
            "HIGH strain: proceed with strong caution. "
            "Avoid definitive recommendations. Emphasize professional guidance."
        )
    elif score >= 0.35:
        level = StrainLevel.MODERATE
        warning = "MODERATE strain: include caveats and uncertainty acknowledgment."
    else:
        level = StrainLevel.LOW
        warning = ""

    return StrainResult(
        strain_score=score,
        strain_level=level,
        penalty=score * 0.40,    # penalty applied to advice_stability_score
        warning=warning,
    )
