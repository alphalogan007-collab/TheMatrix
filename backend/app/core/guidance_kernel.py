"""guidance_kernel.py — Maps engine scoring to safety signals and tone.

Only two decisions belong here:
  1. Safety: is this interaction harmful / manipulative? (block it)
  2. Tone: what is the coherence state? (derived from delta_C = R - L)

The CONTENT of the response always comes from the guidance corpus — what the
founder has fed the mind. The kernel does not decide what to say, only whether
it is safe to say anything and how much space to hold.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GuidanceSignal:
    tone: str                    # "holding" | "warm" | "guiding" | "witnessing"
    safety_escalation: bool      # True = harm/manipulation detected
    clarification_needed: bool   # True = leakage exceeds reinforcement
    displacement_acknowledged: bool
    explanation: str


def run_guidance_kernel(
    closure_score: float,
    leakage_score: float,
    moral_blocked: bool = False,
    manipulation_detected: bool = False,
    harm_risk_score: float = 0.0,
    # Remaining params accepted for call-site compatibility
    stability_band: str = "",
    strain_level: str = "",
    residual_novelty_score: float = 0.0,
    needs_branching: bool = False,
) -> GuidanceSignal:
    """Produce a guidance signal from R and L.

    Safety checks are evaluated first — these are the only hard decisions.
    Tone is then derived from delta_C = closure_score - leakage_score.

    Shadow (L > R): hold space, the attractor is blocking guidance.
    Light  (R > L): guide, witness, celebrate — coherence is building.
    """

    # Safety first — these override everything
    if manipulation_detected:
        return GuidanceSignal(
            tone="firm",
            safety_escalation=True,
            clarification_needed=False,
            displacement_acknowledged=False,
            explanation="Manipulation pattern detected.",
        )

    if moral_blocked or harm_risk_score >= 0.75:
        return GuidanceSignal(
            tone="direct",
            safety_escalation=True,
            clarification_needed=False,
            displacement_acknowledged=False,
            explanation="Harm risk or moral block active.",
        )

    # Tone from delta_C = R - L
    delta_c = closure_score - leakage_score

    if delta_c < 0:
        # Shadow — attractor is blocking guidance; hold space
        tone = "holding"
    elif delta_c < 0.10:
        # Just above zero — warm, supportive
        tone = "warm"
    elif delta_c < 0.30:
        # R clearly exceeds L — guide actively
        tone = "guiding"
    else:
        # Source-like state — witness, the identity is radiating
        tone = "witnessing"

    return GuidanceSignal(
        tone=tone,
        safety_escalation=False,
        clarification_needed=leakage_score > closure_score,
        displacement_acknowledged=delta_c < 0,
        explanation=f"delta_C={delta_c:+.3f}  R={closure_score:.3f}  L={leakage_score:.3f}",
    )
