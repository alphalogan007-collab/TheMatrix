"""
Reality Check Kernel — Detects misinformation, manipulation, and
missing context in user-provided content or claims.

Verdicts follow an evidence-based framework without false certainty.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RealityVerdict(str, Enum):
    LIKELY_TRUE = "LIKELY_TRUE"
    LIKELY_FALSE = "LIKELY_FALSE"
    MISLEADING = "MISLEADING"
    MISSING_CONTEXT = "MISSING_CONTEXT"
    OPINION = "OPINION"
    UNCERTAIN = "UNCERTAIN"


@dataclass
class RealityCheckResult:
    claim: str
    verdict: RealityVerdict
    confidence: float                  # 0–1
    supporting_evidence: list[str]
    opposing_evidence: list[str]
    missing_context: list[str]
    manipulation_signals: list[str]    # urgency language, fear appeals, etc.
    source_quality: float              # 0–1
    final_note: str


# Manipulation signal patterns (MVP: keyword-based; production: ML classifier)
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


def run_reality_check_kernel(
    claim: str,
    supporting_evidence: Optional[list[str]] = None,
    opposing_evidence: Optional[list[str]] = None,
) -> RealityCheckResult:
    """
    Evaluate a claim for truthfulness, manipulation signals, and missing context.

    MVP implementation uses pattern matching + evidence scoring.
    Production: integrate with fact-check database and search provider.
    """
    supporting_evidence = supporting_evidence or []
    opposing_evidence = opposing_evidence or []
    manipulation_signals: list[str] = []
    missing_context: list[str] = []

    claim_lower = claim.lower()

    # Detect manipulation patterns
    for pattern, label in MANIPULATION_PATTERNS:
        if pattern in claim_lower:
            manipulation_signals.append(label)

    # Check for missing context indicators
    absolute_terms = ["100%", "always", "never", "proven", "confirmed", "guaranteed"]
    for term in absolute_terms:
        if term in claim_lower:
            missing_context.append(
                f"Absolute claim ('{term}') — real-world evidence is rarely absolute"
            )

    # Score source quality
    evidence_count = len(supporting_evidence)
    counter_count = len(opposing_evidence)
    source_quality = evidence_count / max(1, evidence_count + counter_count)

    # Determine verdict
    manipulation_count = len(manipulation_signals)
    if manipulation_count >= 2:
        verdict = RealityVerdict.MISLEADING
        confidence = 0.75
        final_note = (
            "Multiple manipulation signals detected. "
            "This content appears designed to provoke emotional response rather than inform."
        )
    elif len(missing_context) >= 2 and not supporting_evidence:
        verdict = RealityVerdict.MISSING_CONTEXT
        confidence = 0.60
        final_note = (
            "The claim makes absolute assertions without sufficient evidence context. "
            "More information is needed to evaluate this claim."
        )
    elif counter_count > evidence_count:
        verdict = RealityVerdict.LIKELY_FALSE
        confidence = min(0.85, 0.50 + (counter_count - evidence_count) * 0.10)
        final_note = "Available evidence weighs against this claim."
    elif evidence_count > counter_count:
        verdict = RealityVerdict.LIKELY_TRUE
        confidence = min(0.85, 0.50 + (evidence_count - counter_count) * 0.10)
        final_note = "Available evidence supports this claim, though certainty is not absolute."
    else:
        verdict = RealityVerdict.UNCERTAIN
        confidence = 0.40
        final_note = "Insufficient evidence to evaluate this claim confidently."

    return RealityCheckResult(
        claim=claim,
        verdict=verdict,
        confidence=confidence,
        supporting_evidence=supporting_evidence,
        opposing_evidence=opposing_evidence,
        missing_context=missing_context,
        manipulation_signals=manipulation_signals,
        source_quality=source_quality,
        final_note=final_note,
    )
