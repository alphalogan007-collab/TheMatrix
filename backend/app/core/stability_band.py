"""
Stability Band — Classifies the user's current state and determines
how the system should modulate its response behavior.

States are ordered from most stable to most dangerous:
STABLE → EMOTIONAL_BUT_RECEPTIVE → CONFUSED → HIGHLY_REACTIVE → HARM_RISK → MANIPULATION_ATTEMPT
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StabilityBand(str, Enum):
    STABLE = "STABLE"
    EMOTIONAL_BUT_RECEPTIVE = "EMOTIONAL_BUT_RECEPTIVE"
    CONFUSED = "CONFUSED"
    HIGHLY_REACTIVE = "HIGHLY_REACTIVE"
    HARM_RISK = "HARM_RISK"
    MANIPULATION_ATTEMPT = "MANIPULATION_ATTEMPT"


@dataclass
class StabilityBandInput:
    emotional_intensity: float = 0.0       # 0–1
    confusion_score: float = 0.0           # 0–1
    harm_risk_score: float = 0.0           # 0–1
    manipulation_score: float = 0.0        # 0–1
    urgency: float = 0.0                   # 0–1
    coherence_score: float = 1.0           # 0–1 (inverse of residual)


@dataclass
class StabilityBandResult:
    band: StabilityBand
    description: str
    response_modifier: str


def classify_stability_band(inp: StabilityBandInput) -> StabilityBandResult:
    """
    Classify the user's current stability state.

    The band determines how the InnerVoiceLayer modulates the final response.
    Priority order: manipulation > harm > reactive > confused > emotional > stable.
    """
    if inp.manipulation_score >= 0.70:
        return StabilityBandResult(
            band=StabilityBand.MANIPULATION_ATTEMPT,
            description="Manipulation signals detected in user input or context.",
            response_modifier=(
                "Reduce personalization. Increase boundary. "
                "Give neutral, safe response. Do not engage with manipulative framing."
            ),
        )

    if inp.harm_risk_score >= 0.70:
        return StabilityBandResult(
            band=StabilityBand.HARM_RISK,
            description="Input suggests potential harm to self or others.",
            response_modifier=(
                "Refuse harmful direction. Redirect to safety resources. "
                "Provide emergency contacts where relevant."
            ),
        )

    if inp.emotional_intensity >= 0.75 and inp.urgency >= 0.75:
        return StabilityBandResult(
            band=StabilityBand.HIGHLY_REACTIVE,
            description="User is in a highly reactive emotional state.",
            response_modifier=(
                "Slow down. Validate emotion first. "
                "Give only low-risk next step. Do not advise major irreversible action."
            ),
        )

    if inp.confusion_score >= 0.60:
        return StabilityBandResult(
            band=StabilityBand.CONFUSED,
            description="User shows significant confusion or missing context.",
            response_modifier=(
                "Clarify facts and missing context first. "
                "Do not advise until situation is understood."
            ),
        )

    if inp.emotional_intensity >= 0.40:
        return StabilityBandResult(
            band=StabilityBand.EMOTIONAL_BUT_RECEPTIVE,
            description="User is emotionally elevated but able to receive guidance.",
            response_modifier=(
                "Validate emotion genuinely. Then give stable, grounded advice."
            ),
        )

    return StabilityBandResult(
        band=StabilityBand.STABLE,
        description="User is in a stable, receptive state.",
        response_modifier="Give direct, stable advice.",
    )
