"""
Residual Novelty — What the current identity structure cannot absorb.

Every new user input creates residual novelty:
- what does not fit the user model
- what does not fit known facts
- what creates contradiction
- what creates structural strain
- what must be clarified before advice is safe
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.phi import PHI_INV, PHI_INV2


@dataclass
class ResidualNoveltyInput:
    novelty_score: float = 0.0            # how new/unexpected the input is (0–1)
    contradiction_with_memory: float = 0.0  # conflicts user's own history
    unresolved_context: float = 0.0       # missing information needed to advise
    source_gap: float = 0.0               # lack of supporting knowledge patterns


@dataclass
class ResidualNoveltyResult:
    residual_score: float          # combined residual (0–1)
    needs_branching: bool          # True → create investigation branch
    requires_clarification: bool   # True → ask user for more context
    summary: str


# Thresholds derived from the golden ratio partition of [0,1].
# The same geometry governs resonance thresholds and stage ticks:
#
#   BRANCH threshold       = 1/φ  ≈ 0.618  — large part of the interval
#   CLARIFICATION threshold = 1/φ² ≈ 0.382  — small part of the interval
#
# Together they tile [0,1] self-similarly:
#   [0, 0.382) → low residual, integrates well
#   [0.382, 0.618) → moderate, needs clarification
#   [0.618, 1.0] → high, cannot be safely absorbed → branch
RESIDUAL_BRANCH_THRESHOLD = PHI_INV          # ≈ 0.618
RESIDUAL_CLARIFICATION_THRESHOLD = PHI_INV2  # ≈ 0.382


def compute_residual_novelty(inp: ResidualNoveltyInput) -> ResidualNoveltyResult:
    """
    Compute the residual — unabsorbed portion of the input.

    High residual → the system cannot confidently advise → branch or clarify.

    DEPRECATED: Use `residual_from_resonance()` instead. This hand-weight formula
    is kept for backward compat with routes_advisor.py and the identity_engine
    22-layer pipeline, which pass pre-computed sub-scores. The resonance loop in
    _compose_mind_response() now calls residual_from_resonance() directly.
    """
    score = min(
        1.0,
        (
            inp.novelty_score * 0.30
            + inp.contradiction_with_memory * 0.30
            + inp.unresolved_context * 0.25
            + inp.source_gap * 0.15
        ),
    )

    return _build_result(score)


def residual_from_resonance(max_resonance_score: float) -> ResidualNoveltyResult:
    """Compute residual from the resonance loop's best-match score.

    This is the correct calculation:
        residual = 1.0 − max_resonance

    max_resonance = 1.0  → perfect fit → residual 0.0 (DEFORM, no branching needed)
    max_resonance = 0.0  → nothing matched → residual 1.0 (BRANCH or IGNORE_AS_NOISE)
    max_resonance = 0.5  → partial fit → residual 0.5 (may need clarification)

    Call this after superimpose_resonance() returns its sorted list.
    """
    score = round(1.0 - max(0.0, min(1.0, max_resonance_score)), 4)
    return _build_result(score)


def _build_result(score: float) -> ResidualNoveltyResult:
    needs_branching = score >= RESIDUAL_BRANCH_THRESHOLD
    requires_clarification = (
        score >= RESIDUAL_CLARIFICATION_THRESHOLD and not needs_branching
    )

    if needs_branching:
        summary = (
            "High residual: input cannot be safely absorbed into current model. "
            "Creating investigation branch."
        )
    elif requires_clarification:
        summary = "Moderate residual: more context needed before stable advice is possible."
    else:
        summary = "Low residual: input integrates well with existing model."

    return ResidualNoveltyResult(
        residual_score=score,
        needs_branching=needs_branching,
        requires_clarification=requires_clarification,
        summary=summary,
    )

