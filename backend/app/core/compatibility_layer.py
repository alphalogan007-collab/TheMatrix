"""
Compatibility Layer — New advice must be compatible with:
- factual reality
- non-harm
- moral guidance
- user context
- long-term wellbeing
- emotional stability
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CompatibilityInput:
    fit_with_core_blueprint: float = 0.0    # alignment with centralized base pattern
    fit_with_user_values: float = 0.0       # alignment with user's stated values/goals
    fit_with_factual_reality: float = 0.0   # factual accuracy score
    fit_with_non_harm: float = 0.0          # non-harm check score


@dataclass
class CompatibilityResult:
    compatibility_score: float
    bonus: float                # positive contribution to advice_stability_score
    is_incompatible: bool       # True → must not use this advice direction
    reason: str


COMPATIBILITY_BLOCK_THRESHOLD = 0.30  # below this = incompatible


def compute_compatibility(inp: CompatibilityInput) -> CompatibilityResult:
    """
    Compute the compatibility of a proposed advice direction.

    Blueprint compatibility carries highest weight — it anchors to the
    low-leakage base pattern.
    """
    score = (
        inp.fit_with_core_blueprint * 0.35
        + inp.fit_with_user_values * 0.20
        + inp.fit_with_factual_reality * 0.25
        + inp.fit_with_non_harm * 0.20
    )
    score = max(0.0, min(1.0, score))
    bonus = score * 0.20

    is_incompatible = score < COMPATIBILITY_BLOCK_THRESHOLD

    if is_incompatible:
        reason = (
            "Advice direction is incompatible with the Core Blueprint or non-harm requirements. "
            "Cannot proceed with this direction."
        )
    elif score < 0.60:
        reason = "Partial compatibility — include caveats and monitor response carefully."
    else:
        reason = "Compatible with Core Blueprint and user context."

    return CompatibilityResult(
        compatibility_score=score,
        bonus=bonus,
        is_incompatible=is_incompatible,
        reason=reason,
    )
