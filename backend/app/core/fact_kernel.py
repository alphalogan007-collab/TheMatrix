"""fact_kernel.py — Linguistic pattern detection for user input.

Y Theory: the mind cannot evaluate whether a user's claim is factually true.
It has no external fact database and no ground truth.

What the mind CAN detect from text structure:
  - Absolute language (always, never, everyone, impossible) — collapses the
    probability space, signals over-certainty.
  - Internal contradictions — the claim contains opposing poles simultaneously,
    which is a structural leakage signal (the statement cannot hold coherently).

These are real pattern-level detections, not truth judgments.
The factual grounding scores (0.30, 0.65, 0.85) and confidence numbers that
previously lived here were invented — they implied the system knew something
about the claim's truth value. It does not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class FactVerdict(str, Enum):
    GROUNDED = "GROUNDED"                          # no flags detected
    UNCERTAIN = "UNCERTAIN"                        # absolute terms present
    INTERNALLY_CONTRADICTORY = "INTERNALLY_CONTRADICTORY"  # opposing poles
    ABSOLUTE_CLAIM = "ABSOLUTE_CLAIM"              # 3+ absolute terms


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


def run_fact_kernel(text: str) -> FactKernelResult:
    """Detect absolute-language patterns and internal contradictions.

    No grounding scores. No confidence numbers. Only what the text structure
    actually reveals. If a contradiction pair appears, the claim is structurally
    incoherent. If absolute terms appear frequently, the claim over-collapses
    probability — both are leakage signals, not truth judgments.
    """
    text_lower = text.lower()

    absolute_hits = [p.pattern for p in _ABSOLUTE_PATTERNS if p.search(text_lower)]
    absolute_count = len(absolute_hits)

    contradiction_signals: list[str] = []
    for word_a, word_b in _CONTRADICTION_PAIRS:
        if word_a in text_lower and word_b in text_lower:
            contradiction_signals.append(f"{word_a}/{word_b}")

    if contradiction_signals:
        verdict = FactVerdict.INTERNALLY_CONTRADICTORY
    elif absolute_count >= 3:
        verdict = FactVerdict.ABSOLUTE_CLAIM
    elif absolute_count >= 1:
        verdict = FactVerdict.UNCERTAIN
    else:
        verdict = FactVerdict.GROUNDED

    return FactKernelResult(
        verdict=verdict,
        absolute_claim_count=absolute_count,
        contradiction_signals=contradiction_signals,
    )
