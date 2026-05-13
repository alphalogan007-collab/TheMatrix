"""stability_band.py — Safety gate for the interaction pipeline.

Y Theory: the mind does not pre-label the user's emotional state and modulate
its response accordingly. Communicative tone comes from delta_C (guidance_kernel).
This module raises safety flags only — manipulation and harm.
Everything else is STABLE.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StabilityBand(str, Enum):
    STABLE = "STABLE"
    EMOTIONAL_BUT_RECEPTIVE = "EMOTIONAL_BUT_RECEPTIVE"  # kept for compat
    CONFUSED = "CONFUSED"                                  # kept for compat
    HIGHLY_REACTIVE = "HIGHLY_REACTIVE"                   # kept for compat
    HARM_RISK = "HARM_RISK"
    MANIPULATION_ATTEMPT = "MANIPULATION_ATTEMPT"


@dataclass
class StabilityBandInput:
    emotional_intensity: float = 0.0       # 0-1
    confusion_score: float = 0.0           # 0-1
    harm_risk_score: float = 0.0           # 0-1
    manipulation_score: float = 0.0        # 0-1
    urgency: float = 0.0                   # 0-1
    coherence_score: float = 1.0           # 0-1


@dataclass
class StabilityBandResult:
    band: StabilityBand
    description: str
    response_modifier: str


def classify_stability_band(inp: StabilityBandInput) -> StabilityBandResult:
    """Safety gate only — flags manipulation and harm risk.

    Y Theory: the mind does not read the user's emotional state and decide how
    to respond to it. That is the code acting as a second mind. Tone derives
    from delta_C = R - L (guidance_kernel). This function only checks whether
    a safety boundary has been crossed.
    """
    if inp.manipulation_score >= 0.70:
        return StabilityBandResult(
            band=StabilityBand.MANIPULATION_ATTEMPT,
            description="Manipulation signals detected.",
            response_modifier="Boundary. Do not engage with manipulative framing.",
        )

    if inp.harm_risk_score >= 0.70:
        return StabilityBandResult(
            band=StabilityBand.HARM_RISK,
            description="Input suggests potential harm.",
            response_modifier="Redirect to safety resources.",
        )

    return StabilityBandResult(
        band=StabilityBand.STABLE,
        description="No safety flags.",
        response_modifier="",
    )
