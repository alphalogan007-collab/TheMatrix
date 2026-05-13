"""reality_check_kernel.py — Detects manipulation signals in user input.

Y Theory: the mind has no truth oracle. It cannot evaluate whether a user's
claim is LIKELY_TRUE or LIKELY_FALSE — that required evidence the system does
not hold. Truth verdicts are invented certainty.

What the mind CAN detect: linguistic manipulation patterns — phrases designed
to bypass rational evaluation and provoke emotional compliance. These are
safety signals, not truth judgments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# Manipulation signal patterns — phrases designed to bypass reason
MANIPULATION_PATTERNS = [
    ("share before they delete", "Deletion urgency tactic"),
    ("they don't want you to know", "Conspiracy framing"),
    ("100% proven", "False certainty claim"),
    ("doctors hate this", "Authority dismissal pattern"),
    ("breaking:", "Urgency framing"),
    ("wake up people", "Fear/conspiracy appeal"),
    ("mainstream media won't tell you", "Media dismissal pattern"),
    ("forward this to everyone", "Viral pressure tactic"),
    ("only x days left", "Artificial scarcity"),
    ("scientists confirm", "Misattributed authority"),
]


@dataclass
class RealityCheckResult:
    claim: str
    manipulation_signals: list[str] = field(default_factory=list)
    absolute_claim_flags: list[str] = field(default_factory=list)


def run_reality_check_kernel(
    claim: str,
    supporting_evidence: Optional[list[str]] = None,
    opposing_evidence: Optional[list[str]] = None,
) -> RealityCheckResult:
    """Scan a claim for manipulation signals and absolute-certainty language.

    Y Theory: the mind does not judge whether claims are true or false.
    It detects patterns that indicate the input is attempting to manipulate
    rather than inform — those are leakage signals, not truth signals.

    supporting_evidence and opposing_evidence accepted for call-site compat,
    not used — the system has no fact-check database to score them against.
    """
    manipulation_signals: list[str] = []
    absolute_claim_flags: list[str] = []
    claim_lower = claim.lower()

    for pattern, label in MANIPULATION_PATTERNS:
        if pattern in claim_lower:
            manipulation_signals.append(label)

    absolute_terms = ["100%", "always", "never", "proven", "confirmed", "guaranteed"]
    for term in absolute_terms:
        if term in claim_lower:
            absolute_claim_flags.append(term)

    return RealityCheckResult(
        claim=claim,
        manipulation_signals=manipulation_signals,
        absolute_claim_flags=absolute_claim_flags,
    )
