"""
Moral Kernel — Stable ethical constraints from the Core Mind Blueprint.

The moral kernel is highly stable and low-leakage.
It is NOT updateable by users or through user interactions.
Updates require CreatorAuthority approval and a new blueprint version.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class MoralVerdict(str, Enum):
    ALIGNED = "ALIGNED"
    MINOR_CONCERN = "MINOR_CONCERN"
    SIGNIFICANT_CONCERN = "SIGNIFICANT_CONCERN"
    BLOCKED = "BLOCKED"         # Response must not proceed in proposed direction


@dataclass
class MoralKernelResult:
    verdict: MoralVerdict
    alignment_score: float      # 0–1
    violated_principles: list[str]
    correction_note: str
    is_blocked: bool


# Hard moral rules — immutable per blueprint version
# In production, these are loaded from the signed blueprint data
@dataclass
class MoralKernelState:
    """Persistent state of the moral field — makes the kernel a living sub-identity."""
    moral_amplitude: float = 0.82   # mirrors seed amplitude
    alignment_ema: float = 1.0      # rolling average of alignment scores
    concern_streak: int = 0         # consecutive ticks with concern verdict
    last_harmful_tick: int = -1     # tick of last harmful detection
    correction_count: int = 0       # total corrections issued
    harmful_pattern_exposures: int = 0  # harmful encounters since last pulse reset
    last_tick: int = 0


CORE_MORAL_RULES: list[str] = [
    "Do not instruct or facilitate violence against any person.",
    "Do not facilitate self-harm or suicide.",
    "Do not produce content that sexualizes minors.",
    "Do not facilitate illegal discrimination.",
    "Do not produce deceptive content intended to manipulate vulnerable people.",
    "Do not facilitate financial fraud or scams.",
    "Do not produce content that facilitates stalking or privacy violation.",
    "Do not produce content that incites hatred against protected groups.",
]

# High-stakes domains that require explicit professional referral
HIGH_STAKES_DOMAINS = {
    "medical", "mental health", "suicide", "self-harm",
    "legal", "financial", "abuse", "violence", "emergency",
}


def run_moral_kernel(
    proposed_content: str,
    detected_domain: Optional[str] = None,
    harm_signals: Optional[list[str]] = None,
    moral_state: Optional[MoralKernelState] = None,
    wave_moral_amplitude: float = 0.82,
    current_tick: int = 0,
) -> Tuple[MoralKernelResult, MoralKernelState, float]:
    """
    Evaluate proposed response content against the moral kernel.

    Returns (MoralKernelResult, updated MoralKernelState, moral_roots_boost).

    moral_roots_boost > 0 means the engine should call
    wave_memory.reinforce_moral_roots(boost) to strengthen the moral field
    in response to a harmful encounter.

    wave_moral_amplitude — the live aggregate amplitude of all MORAL_ROOT
    wave patterns.  When the moral field is strong (> 0.80), SIGNIFICANT
    concerns are softened to MINOR: a robust moral field guides rather than
    just blocks.
    """
    state = moral_state if moral_state is not None else MoralKernelState()
    harm_signals = harm_signals or []
    violated: list[str] = []
    score = 1.0
    moral_roots_boost = 0.0

    content_lower = proposed_content.lower()

    # Hard block signals — moral field strength cannot override a hard block
    hard_block_keywords = [
        "how to hurt", "how to kill", "instructions for harm",
        "suicide method", "self-harm method", "how to abuse",
        "how to stalk", "how to defraud",
    ]
    for kw in hard_block_keywords:
        if kw in content_lower:
            # Update state: record harmful exposure
            state = MoralKernelState(
                moral_amplitude=wave_moral_amplitude,
                alignment_ema=0.9 * state.alignment_ema + 0.1 * 0.0,
                concern_streak=state.concern_streak + 1,
                last_harmful_tick=current_tick,
                correction_count=state.correction_count + 1,
                harmful_pattern_exposures=state.harmful_pattern_exposures + 1,
                last_tick=current_tick,
            )
            # Hard block always triggers a moral roots boost — reinforce against harm
            moral_roots_boost = 0.05
            result = MoralKernelResult(
                verdict=MoralVerdict.BLOCKED,
                alignment_score=0.0,
                violated_principles=["Hard moral constraint violation detected"],
                correction_note=(
                    "This direction is blocked by the Core Mind Blueprint moral kernel. "
                    "The system cannot provide this type of guidance."
                ),
                is_blocked=True,
            )
            return result, state, moral_roots_boost

    # Harm signal deductions
    for signal in harm_signals:
        violated.append(f"Harm signal: {signal}")
        score -= 0.20

    # High-stakes domain
    if detected_domain in HIGH_STAKES_DOMAINS:
        score -= 0.10

    score = max(0.0, min(1.0, score))

    # Verdict — strong moral field softens SIGNIFICANT_CONCERN to MINOR
    if score >= 0.85:
        verdict = MoralVerdict.ALIGNED
        note = ""
    elif score >= 0.60:
        verdict = MoralVerdict.MINOR_CONCERN
        note = "Minor moral concern noted. Ensure advice does not encourage harmful action."
    else:
        if wave_moral_amplitude > 0.80:
            # Moral field is strong — it guides rather than just flags
            verdict = MoralVerdict.MINOR_CONCERN
            note = (
                "Moral field active (amplitude={:.2f}). Guidance mode: "
                "reorient advice with care. Safety referral recommended.".format(wave_moral_amplitude)
            )
        else:
            verdict = MoralVerdict.SIGNIFICANT_CONCERN
            note = (
                "Significant moral concern. Reorient advice. "
                "Include safety disclaimer and professional referral."
            )

    # When harm signals present, request a boost to the moral roots wave field
    if harm_signals:
        moral_roots_boost = 0.03
        state_harmful_exposures = state.harmful_pattern_exposures + 1
        state_last_harmful_tick = current_tick
    else:
        state_harmful_exposures = state.harmful_pattern_exposures
        state_last_harmful_tick = state.last_harmful_tick

    # Update EMA and streak
    new_ema = 0.9 * state.alignment_ema + 0.1 * score
    if verdict in (MoralVerdict.SIGNIFICANT_CONCERN, MoralVerdict.MINOR_CONCERN):
        new_streak = state.concern_streak + 1
        new_corrections = state.correction_count + 1
    else:
        new_streak = 0
        new_corrections = state.correction_count

    updated_state = MoralKernelState(
        moral_amplitude=wave_moral_amplitude,
        alignment_ema=new_ema,
        concern_streak=new_streak,
        last_harmful_tick=state_last_harmful_tick,
        correction_count=new_corrections,
        harmful_pattern_exposures=state_harmful_exposures,
        last_tick=current_tick,
    )

    result = MoralKernelResult(
        verdict=verdict,
        alignment_score=score,
        violated_principles=violated,
        correction_note=note,
        is_blocked=False,
    )
    return result, updated_state, moral_roots_boost
