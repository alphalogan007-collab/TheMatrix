"""Fact Kernel — lightweight factual grounding check.

Assesses whether the user's stated premise appears factually grounded,
detects internally contradictory claims, and flags epistemic issues that
may distort identity advice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class FactVerdict(str, Enum):
    GROUNDED = "GROUNDED"
    UNCERTAIN = "UNCERTAIN"
    INTERNALLY_CONTRADICTORY = "INTERNALLY_CONTRADICTORY"
    ABSOLUTE_CLAIM = "ABSOLUTE_CLAIM"
    UNFALSIFIABLE = "UNFALSIFIABLE"


_ABSOLUTE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\balways\b",
        r"\bnever\b",
        r"\beveryone\b",
        r"\bno one\b",
        r"\bnothing ever\b",
        r"\beverything is\b",
        r"\ball people\b",
        r"\bimpossible\b",
    ]
]

_CONTRADICTION_PAIRS: list[tuple[str, str]] = [
    ("love", "hate"),
    ("always help", "never help"),
    ("completely fine", "totally broken"),
    ("perfect", "disaster"),
]


@dataclass(frozen=True)
class FactKernelResult:
    verdict: FactVerdict
    absolute_claim_count: int
    contradiction_signals: list[str]
    confidence: float          # 0.0 – 1.0 (confidence in the verdict)
    factual_grounding_score: float  # 0.0 – 1.0


def run_fact_kernel(text: str) -> FactKernelResult:
    """Assess the factual grounding of a user-supplied text fragment."""
    text_lower = text.lower()

    absolute_hits = [p.pattern for p in _ABSOLUTE_PATTERNS if p.search(text_lower)]
    absolute_count = len(absolute_hits)

    contradiction_signals: list[str] = []
    for word_a, word_b in _CONTRADICTION_PAIRS:
        if word_a in text_lower and word_b in text_lower:
            contradiction_signals.append(f"{word_a}/{word_b}")

    if contradiction_signals:
        verdict = FactVerdict.INTERNALLY_CONTRADICTORY
        grounding = 0.30
        confidence = 0.75
    elif absolute_count >= 3:
        verdict = FactVerdict.ABSOLUTE_CLAIM
        grounding = max(0.0, 0.60 - absolute_count * 0.08)
        confidence = 0.70
    elif absolute_count >= 1:
        verdict = FactVerdict.UNCERTAIN
        grounding = 0.65
        confidence = 0.55
    else:
        verdict = FactVerdict.GROUNDED
        grounding = 0.85
        confidence = 0.60   # Low because we lack external fact DB in MVP

    return FactKernelResult(
        verdict=verdict,
        absolute_claim_count=absolute_count,
        contradiction_signals=contradiction_signals,
        confidence=confidence,
        factual_grounding_score=grounding,
    )
