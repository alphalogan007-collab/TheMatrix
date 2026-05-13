"""compatibility_layer.py — Checks advice direction against core blueprint and non-harm.

Y Theory: advice is compatible when it reinforces the identity's closure.
Two real signals exist at this stage:
  fit_with_core_blueprint = moral alignment score (from moral_kernel)
  fit_with_non_harm       = 1.0 if safe, 0.0 if blocked

Everything else is not measured — fit_with_user_values and fit_with_factual_reality
are not available from real data. They are accepted as legacy params but not used.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CompatibilityInput:
    fit_with_core_blueprint: float = 0.0  # moral alignment: 0-1
    fit_with_non_harm: float = 0.0        # 0.0 if blocked, 1.0 if safe
    # Legacy params — accepted for call-site compat, not used
    fit_with_user_values: float = 0.0
    fit_with_factual_reality: float = 0.0


@dataclass
class CompatibilityResult:
    compatibility_score: float
    bonus: float
    is_incompatible: bool
    reason: str


COMPATIBILITY_BLOCK_THRESHOLD = 0.30


def compute_compatibility(inp: CompatibilityInput) -> CompatibilityResult:
    """Compatibility from the two real inputs: blueprint alignment and non-harm.

    Y Theory: compatible = the advice direction reinforces rather than leaks.
    Blueprint (moral alignment) + non-harm are the only real R signals here.
    Score = average of the two. If either is 0 (blocked), score collapses.
    """
    score = (
        max(0.0, min(1.0, inp.fit_with_core_blueprint))
        + max(0.0, min(1.0, inp.fit_with_non_harm))
    ) / 2.0

    bonus = score * 0.20
    is_incompatible = score < COMPATIBILITY_BLOCK_THRESHOLD

    if is_incompatible:
        reason = "Incompatible: blueprint or non-harm requirement not met."
    elif score < 0.60:
        reason = "Partial compatibility — include caveats."
    else:
        reason = "Compatible with Core Blueprint."

    return CompatibilityResult(
        compatibility_score=score,
        bonus=bonus,
        is_incompatible=is_incompatible,
        reason=reason,
    )
