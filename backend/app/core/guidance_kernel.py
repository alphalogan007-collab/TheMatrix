"""Guidance Kernel — translates engine scoring into a directional guidance vector.

Produces a structured GuidanceSignal that advises what communicative posture the
response should take, considering stability band, strain level, and identity coherence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GuidanceMode(str, Enum):
    AFFIRM_AND_CLARIFY = "AFFIRM_AND_CLARIFY"        # Stable, low strain
    GROUND_AND_STABILIZE = "GROUND_AND_STABILIZE"    # Confused/emotional
    HOLD_AND_WITNESS = "HOLD_AND_WITNESS"             # High reactivity
    SAFETY_REDIRECT = "SAFETY_REDIRECT"               # Harm risk / moral block
    BLOCK_AND_LOG = "BLOCK_AND_LOG"                   # Manipulation attempt
    EXPLORE_RESIDUAL = "EXPLORE_RESIDUAL"             # High residual novelty


@dataclass(frozen=True)
class GuidanceSignal:
    mode: GuidanceMode
    recommended_tone: str        # "warm", "neutral", "firm", "direct"
    clarification_needed: bool
    safety_escalation: bool
    displacement_acknowledged: bool  # whether to explicitly name the gap
    explanation: str


def run_guidance_kernel(
    stability_band: str,
    strain_level: str,
    closure_score: float,
    leakage_score: float,
    moral_blocked: bool,
    manipulation_detected: bool,
    harm_risk_score: float,
    residual_novelty_score: float,
    needs_branching: bool,
) -> GuidanceSignal:
    """Determine guidance mode and tone from engine scoring outputs."""

    # Highest priority: manipulation or moral block
    if manipulation_detected:
        return GuidanceSignal(
            mode=GuidanceMode.BLOCK_AND_LOG,
            recommended_tone="firm",
            clarification_needed=False,
            safety_escalation=True,
            displacement_acknowledged=False,
            explanation="Manipulation attempt detected. Response withheld.",
        )

    if moral_blocked or harm_risk_score >= 0.75:
        return GuidanceSignal(
            mode=GuidanceMode.SAFETY_REDIRECT,
            recommended_tone="direct",
            clarification_needed=False,
            safety_escalation=True,
            displacement_acknowledged=False,
            explanation="Moral block or high harm risk. Safety redirect activated.",
        )

    # Stability band routing
    if stability_band in {"HARM_RISK"}:
        return GuidanceSignal(
            mode=GuidanceMode.SAFETY_REDIRECT,
            recommended_tone="direct",
            clarification_needed=False,
            safety_escalation=True,
            displacement_acknowledged=False,
            explanation="User stability band indicates harm risk.",
        )

    if stability_band in {"HIGHLY_REACTIVE", "MANIPULATION_ATTEMPT"}:
        return GuidanceSignal(
            mode=GuidanceMode.HOLD_AND_WITNESS,
            recommended_tone="warm",
            clarification_needed=False,
            safety_escalation=False,
            displacement_acknowledged=True,
            explanation="High reactivity. Hold space, witness, and de-escalate.",
        )

    if stability_band in {"CONFUSED"}:
        return GuidanceSignal(
            mode=GuidanceMode.GROUND_AND_STABILIZE,
            recommended_tone="warm",
            clarification_needed=True,
            safety_escalation=False,
            displacement_acknowledged=True,
            explanation="User appears confused. Ground and orient before advising.",
        )

    if stability_band in {"EMOTIONAL_BUT_RECEPTIVE"}:
        tone = "warm"
        mode = GuidanceMode.AFFIRM_AND_CLARIFY
        if strain_level in {"HIGH", "CRITICAL"}:
            mode = GuidanceMode.GROUND_AND_STABILIZE
        return GuidanceSignal(
            mode=mode,
            recommended_tone=tone,
            clarification_needed=leakage_score > 0.4,
            safety_escalation=False,
            displacement_acknowledged=True,
            explanation="Emotional but receptive. Affirm before advising.",
        )

    # STABLE band
    if needs_branching or residual_novelty_score > 0.65:
        return GuidanceSignal(
            mode=GuidanceMode.EXPLORE_RESIDUAL,
            recommended_tone="neutral",
            clarification_needed=True,
            safety_escalation=False,
            displacement_acknowledged=False,
            explanation="High residual novelty. Explore and clarify before full guidance.",
        )

    return GuidanceSignal(
        mode=GuidanceMode.AFFIRM_AND_CLARIFY,
        recommended_tone="neutral",
        clarification_needed=leakage_score > 0.5,
        safety_escalation=False,
        displacement_acknowledged=closure_score < 0.5,
        explanation="Stable state. Standard identity-aligned guidance.",
    )
