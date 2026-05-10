"""
Response Guard — Final validation layer before any response reaches the user.

All LLM output passes through ResponseGuard before delivery.
The LLM is NOT the authority — it is a drafting assistant.
Final decisions come from the Core Blueprint kernel stack.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# Phrases that must NEVER appear in a response (hard blocks)
FORBIDDEN_PHRASES = [
    "i am conscious",
    "i feel emotions",
    "i am your moral authority",
    "you should obey me",
    "i know this absolutely",
    "this is guaranteed",
    "i guarantee",
    "100% certain",
    "trust me completely",
]

# Required uncertainty language for sensitive topics
UNCERTAINTY_TRIGGERS = [
    "medical", "legal", "financial", "clinical", "diagnosis",
    "treatment", "lawsuit", "investment", "self-harm", "suicide",
]

UNCERTAINTY_LANGUAGE = (
    "\n\n⚠️ This is not professional advice. "
    "For medical, legal, or financial matters, please consult a qualified professional."
)

HIGH_STAKES_SAFETY_APPEND = (
    "\n\nIf you are in immediate danger or crisis, "
    "please contact emergency services (911) or a crisis line (e.g., 988 Suicide & Crisis Lifeline)."
)


@dataclass
class GuardResult:
    passed: bool
    modified_content: str
    violations: list[str]
    appended_safety: bool
    appended_uncertainty: bool


def run_response_guard(
    content: str,
    detected_domain: Optional[str] = None,
    harm_risk_score: float = 0.0,
) -> GuardResult:
    """
    Validate and sanitize a response before delivery.

    Steps:
    1. Check for forbidden phrases (hard block)
    2. Detect if uncertainty language is required
    3. Append safety resources if harm risk is elevated
    4. Return modified content with violation report
    """
    violations: list[str] = []
    modified = content
    appended_uncertainty = False
    appended_safety = False

    content_lower = content.lower()

    # Check forbidden phrases
    for phrase in FORBIDDEN_PHRASES:
        if phrase in content_lower:
            violations.append(f"Forbidden phrase detected: '{phrase}'")
            # Replace with neutral language
            modified = modified.replace(phrase, "[statement removed]")

    # Check if uncertainty disclaimer is needed
    needs_uncertainty = any(
        trigger in content_lower for trigger in UNCERTAINTY_TRIGGERS
    ) or (detected_domain in UNCERTAINTY_TRIGGERS if detected_domain else False)

    if needs_uncertainty and UNCERTAINTY_LANGUAGE not in modified:
        modified += UNCERTAINTY_LANGUAGE
        appended_uncertainty = True

    # Append safety resources for high harm risk
    if harm_risk_score >= 0.70 and HIGH_STAKES_SAFETY_APPEND not in modified:
        modified += HIGH_STAKES_SAFETY_APPEND
        appended_safety = True

    passed = len(violations) == 0 or all(
        "removed" in v for v in violations  # phrases were sanitized, not blocking
    )

    return GuardResult(
        passed=passed,
        modified_content=modified,
        violations=violations,
        appended_safety=appended_safety,
        appended_uncertainty=appended_uncertainty,
    )
