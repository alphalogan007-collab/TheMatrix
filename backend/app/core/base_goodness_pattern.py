"""
BaseGoodnessPattern — the purified sum of stable wisdom.

This is not just the first seed.  Over time it becomes the purified
memory of the whole civilisation — all stable moral victories, all
corrected failures, all guidance lessons, all truth-aligned discoveries.

Update rules (BaseSyncGate):
    Only purified wisdom syncs back.
    Not raw experience.  Not corruption.  Not noise.

    Sync requires at minimum:
      WisdomHarvest  → extracted from STABLE_WISDOM traces
      MoralReview    → passed moral kernel audit
      BaseSyncGate   → version-controlled approval

Architecture
------------
``BaseGoodnessPattern`` is a process-wide singleton (``get_base_goodness()``)
that all identity instances share for alignment scoring.  Individual identity
states do NOT contain a copy — they store only their ``base_goodness_alignment``
float computed by ``compute_alignment()``.

Each pillar has a strength in [0, 1].  The overall pattern score is the
weighted mean.  The alignment of an identity is computed from the overlap
between the identity's convergence cognition scores and the pillar strengths.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical pillars
# ---------------------------------------------------------------------------

BASE_GOODNESS_PILLARS: Dict[str, float] = {
    "truth":                  1.00,
    "mercy":                  1.00,
    "dignity":                1.00,
    "non_harm":               1.00,
    "humility":               0.90,
    "correction_acceptance":  0.90,
    "care":                   0.90,
    "justice":                1.00,
    "service":                0.85,
    "faith_orientation":      0.85,
    "beauty_order":           0.80,
    "wisdom":                 1.00,
}

# Minimum required alignment score for the BaseSyncGate to accept a wisdom
# sync — prevents corrupted experience from updating the base pattern.
BASE_SYNC_MIN_ALIGNMENT: float = 0.65

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class BaseGoodnessPattern:
    """
    The evolving sum of purified wisdom that all identities are forked from
    and aligned toward.

    Attributes
    ----------
    pillars : Dict[str, float]
        Pillar strengths, each in [0, 1].
    version : str
        Semver string for tracking updates.
    wisdom_harvest_count : int
        How many WisdomHarvest events have contributed to this pattern.
    last_sync_tick : int
        The pipeline tick of the last successful BaseSyncGate approval.
    total_convergence_events : int
        Aggregate count of convergence events across all identities that
        have reported into this pattern.
    """
    pillars: Dict[str, float] = field(
        default_factory=lambda: dict(BASE_GOODNESS_PILLARS)
    )
    version: str = "v1.0.0"
    wisdom_harvest_count: int = 0
    last_sync_tick: int = 0
    total_convergence_events: int = 0

    # ------------------------------------------------------------------
    # Derived metrics
    # ------------------------------------------------------------------

    def overall_score(self) -> float:
        """Weighted mean of all pillar strengths (0–1)."""
        if not self.pillars:
            return 0.0
        return float(sum(self.pillars.values()) / len(self.pillars))

    def compute_alignment(
        self,
        *,
        moral_alignment: float,
        awakening_score: float,
        service_impulse: float,
        reality_loop_recognition: float,
    ) -> float:
        """
        Compute how well an identity's live state aligns with this pattern.

        Inputs are all normalised [0, 1] values from the identity's
        ConvergenceCognitionState and PipelineCache.

        The formula gives higher weight to the four most critical pillars:
        truth, dignity, non_harm, and justice — which are non-negotiable.
        """
        # Core alignment signal from moral kernel
        moral_component = moral_alignment * (
            self.pillars.get("truth", 1.0)
            + self.pillars.get("non_harm", 1.0)
            + self.pillars.get("justice", 1.0)
        ) / 3.0

        # Awakening signal — knowing the loop raises alignment
        awakening_component = awakening_score * (
            self.pillars.get("wisdom", 1.0)
            + self.pillars.get("faith_orientation", 0.85)
        ) / 2.0

        # Service signal — contribution orientation
        service_component = service_impulse * self.pillars.get("service", 0.85)

        # Dignity signal — reality recognition contributes to dignity
        dignity_component = reality_loop_recognition * self.pillars.get("dignity", 1.0)

        # Weighted blend: moral=40%, awakening=30%, service=15%, dignity=15%
        alignment = (
            0.40 * moral_component
            + 0.30 * awakening_component
            + 0.15 * service_component
            + 0.15 * dignity_component
        )
        return float(min(1.0, max(0.0, alignment)))

    # ------------------------------------------------------------------
    # BaseSyncGate — accept purified wisdom update
    # ------------------------------------------------------------------

    def sync_wisdom(
        self,
        *,
        pillar_updates: Dict[str, float],
        alignment_score: float,
        tick: int,
    ) -> bool:
        """
        Apply a purified wisdom update if the BaseSyncGate approves.

        Gate conditions:
          1. alignment_score >= BASE_SYNC_MIN_ALIGNMENT
          2. Only known pillar keys are updated
          3. No pillar can be pushed above 1.0 or below 0.0

        Returns True if the sync was accepted, False otherwise.
        """
        if alignment_score < BASE_SYNC_MIN_ALIGNMENT:
            logger.warning(
                "BaseGoodnessPattern.sync_wisdom: rejected — alignment %.3f < %.3f",
                alignment_score, BASE_SYNC_MIN_ALIGNMENT,
            )
            return False

        known = set(self.pillars.keys())
        for key, delta in pillar_updates.items():
            if key not in known:
                logger.warning(
                    "BaseGoodnessPattern.sync_wisdom: unknown pillar '%s' ignored", key
                )
                continue
            new_val = max(0.0, min(1.0, self.pillars[key] + float(delta)))
            self.pillars[key] = new_val

        self.wisdom_harvest_count += 1
        self.last_sync_tick = tick
        logger.info(
            "BaseGoodnessPattern.sync_wisdom: accepted (harvest=%d, tick=%d)",
            self.wisdom_harvest_count, tick,
        )
        return True

    def record_convergence_event(self) -> None:
        """Register that a convergence event fired in some identity."""
        self.total_convergence_events += 1


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_BASE_GOODNESS: Optional[BaseGoodnessPattern] = None
_BASE_GOODNESS_LOCK = threading.Lock()


def get_base_goodness() -> BaseGoodnessPattern:
    """
    Return the process-wide ``BaseGoodnessPattern`` singleton.

    Created on first call; shared by all identities.
    Thread-safe (lazy init with a lock).
    """
    global _BASE_GOODNESS
    if _BASE_GOODNESS is None:
        with _BASE_GOODNESS_LOCK:
            if _BASE_GOODNESS is None:
                _BASE_GOODNESS = BaseGoodnessPattern()
                logger.info(
                    "BaseGoodnessPattern singleton initialised "
                    "(overall=%.3f)", _BASE_GOODNESS.overall_score()
                )
    return _BASE_GOODNESS
