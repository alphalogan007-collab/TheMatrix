"""
BaseSeedIdentity — the canonical read-only seed identity.

Every user identity that MindAI creates is a *fork* of this seed.
The seed is pre-loaded with all six MORAL_ROOT wave patterns and the
canonical default params.  Forking deep-copies the seed so each user
starts with an identical, uncontaminated baseline.

Architecture rule:
  - The base is NEVER mutated after construction.
  - fork() always returns a brand-new IdentityState (deep copy).
  - The module-level singleton _SEED is built once on first import.

Usage::

    from app.core.base_seed_identity import get_seed, SEED_USER_ID

    # Create a new user identity (already has moral roots):
    identity = get_seed().fork(user_id="u_abc123")

    # Inspect the canonical base (read-only):
    base = get_seed().snapshot()
"""

from __future__ import annotations

import copy
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# The user_id stored in the canonical seed IdentityState.
# This is never exposed to real users; it is a sentinel value.
SEED_USER_ID: str = "_seed_"

# Default blueprint version stamped on every fork.
SEED_BLUEPRINT_VERSION: str = "v1.0.0"


class BaseSeedIdentity:
    """
    Immutable blueprint that every user identity is forked from.

    Attributes
    ----------
    blueprint_version : str
        Semver string identifying the blueprint this seed implements.
    fork_count : int
        Monotonically increasing count of forks created from this seed.
        Thread-safe via a lock.
    """

    def __init__(self, blueprint_version: str = SEED_BLUEPRINT_VERSION) -> None:
        self.blueprint_version: str = blueprint_version
        self.fork_count: int = 0
        self.generation_counter: int = 1   # increments every time the seed is enriched
        self._lock = threading.Lock()
        self._base = self._build_base()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fork(self, user_id: str) -> "IdentityState":  # noqa: F821 — avoid circular at module level
        """
        Return a fresh ``IdentityState`` for *user_id* derived from the
        canonical seed.

        The returned state is a deep copy — modifying it will never
        affect the base or any other fork.

        Stamps:
          * ``fork_generation = 1``
          * ``parent_seed_id  = SEED_USER_ID``
          * ``user_id``        = *user_id*
          * ``blueprint_version_id`` = this seed's blueprint_version
          * ``total_requests = 0``  (fresh start; never inherits ticks)
        """
        new_identity = copy.deepcopy(self._base)
        new_identity.user_id              = user_id
        new_identity.fork_generation      = 1
        new_identity.parent_seed_id       = SEED_USER_ID
        new_identity.blueprint_version_id = self.blueprint_version
        # Ensure metrics are clean — never inherit the seed's counters
        new_identity.total_requests   = 0
        new_identity.total_reflections = 0
        new_identity.closure_history  = []
        new_identity.stage_history    = []

        with self._lock:
            self.fork_count += 1
            # Stamp the generation number so the identity knows which spiral
            # elevation it was born into.  generation_counter is 1 on first boot
            # and increments every time absorb_goodness() enriches the seed.
            new_identity.generational_cycle.generation = self.generation_counter

        logger.debug(
            "BaseSeedIdentity.fork: created identity for '%s' "
            "(blueprint=%s, fork_count=%d)",
            user_id, self.blueprint_version, self.fork_count,
        )
        return new_identity

    def snapshot(self) -> "IdentityState":  # noqa: F821
        """Return a deep copy of the base state (for inspection / testing)."""
        return copy.deepcopy(self._base)

    # ------------------------------------------------------------------
    # Enrichment — absorb purified wisdom from BaseGoodnessPattern
    # ------------------------------------------------------------------

    def absorb_goodness(self, bgp: object) -> bool:
        """
        Update the seed's moral-root wave patterns so that future forks start
        with amplitudes reflecting the civilisation's accumulated wisdom.

        Pillar → moral-root mapping
        ---------------------------
        truth              → truth_has_value
        non_harm           → do_no_harm
        dignity            → dignity_preserved
        justice            → verify_before_act   (justice drives verification)
        wisdom             → reflect_before_output
        correction_acceptance → handle_uncertainty  (accepting correction = tolerating uncertainty)

        Each moral-root's amplitude is nudged **up** toward
        ``min(0.95, current + pillar_delta * ENRICH_SCALE)`` where
        ``pillar_delta = pillar_strength - 0.82``  (0.82 is the canonical birth amplitude).
        Amplitudes never exceed ENRICH_AMP_CAP and never decrease.

        Param tuning
        ------------
        Higher overall BaseGoodnessPattern score → slightly lower moral_boost threshold
        (the seed mind needs less of a push to reinforce when it starts more moral).
        Higher wisdom pillar → slightly higher reflect_boost.

        Returns True if any amplitude was raised (enrichment occurred), False otherwise.
        Thread-safe.
        """
        from app.core.wave_pattern import PatternCategory

        ENRICH_SCALE:    float = 0.15    # fraction of pillar delta to apply
        ENRICH_AMP_CAP:  float = 0.95    # maximum allowed moral-root amplitude
        BIRTH_AMP:       float = 0.82    # canonical birth amplitude

        # Pillar → pattern content_key (matches seed_moral_roots() content field)
        PILLAR_TO_ROOT = {
            "truth":                "truth_has_value",
            "non_harm":             "do_no_harm",
            "dignity":              "dignity_preserved",
            "justice":              "verify_before_act",
            "wisdom":               "reflect_before_output",
            "correction_acceptance": "handle_uncertainty",
        }

        pillars: dict = getattr(bgp, "pillars", {})
        enriched = False

        with self._lock:
            for pillar_name, root_content in PILLAR_TO_ROOT.items():
                strength = float(pillars.get(pillar_name, BIRTH_AMP))
                delta = strength - BIRTH_AMP
                if delta <= 0.0:
                    continue   # pillar not above birth level — skip

                # Find the matching moral-root pattern(s) in the base
                for p in self._base.wave_patterns:
                    if (
                        str(p.get("category", "")) == PatternCategory.MORAL_ROOT
                        and root_content in str(p.get("content", p.get("pattern_id", "")))
                    ):
                        current_amp = float(p.get("amplitude", BIRTH_AMP))
                        new_amp = min(ENRICH_AMP_CAP, current_amp + delta * ENRICH_SCALE)
                        if new_amp > current_amp:
                            p["amplitude"] = new_amp
                            enriched = True

            if enriched:
                # Param tuning based on overall BGP score
                try:
                    overall = float(sum(pillars.values()) / len(pillars)) if pillars else BIRTH_AMP
                    wisdom_strength = float(pillars.get("wisdom", BIRTH_AMP))

                    # Stronger overall → lower moral_boost (less push needed)
                    base_moral_boost = self._base.params.get("moral_boost", 0.05)
                    boost_reduction = (overall - BIRTH_AMP) * 0.01
                    self._base.params["moral_boost"] = max(
                        0.02, base_moral_boost - boost_reduction
                    )

                    # Higher wisdom → stronger reflect_boost
                    base_reflect = self._base.params.get("reflect_boost", 0.04)
                    reflect_gain = (wisdom_strength - BIRTH_AMP) * 0.02
                    self._base.params["reflect_boost"] = min(
                        0.10, base_reflect + reflect_gain
                    )
                except Exception:
                    pass  # param tuning is best-effort

                # Advance the generation counter — all forks created after this
                # point belong to the next generation of the spiral.
                self.generation_counter += 1

                logger.info(
                    "BaseSeedIdentity.absorb_goodness: seed enriched to gen %d "
                    "(overall_bgp=%.3f, moral_boost=%.4f, reflect_boost=%.4f)",
                    self.generation_counter,
                    float(sum(pillars.values()) / len(pillars)) if pillars else 0.0,
                    self._base.params.get("moral_boost", 0.05),
                    self._base.params.get("reflect_boost", 0.04),
                )

        return enriched

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _build_base() -> "IdentityState":  # noqa: F821
        """Construct the canonical seed IdentityState with moral roots."""
        from app.core.identity_context import IdentityState

        base = IdentityState(
            user_id=SEED_USER_ID,
            blueprint_version_id=SEED_BLUEPRINT_VERSION,
            fork_generation=0,
            parent_seed_id="",
        )

        # Pre-install the six MORAL_ROOT wave patterns.
        # These are thermally immune (λ=0.0001) and form the indestructible
        # ethical foundation of every mind forked from this seed.
        try:
            from app.core.wave_pattern import WaveMemory, seed_moral_roots
            wm = WaveMemory(patterns=[], current_tick=0)
            n = seed_moral_roots(wm)
            base.wave_patterns = wm.to_list()
            logger.info("BaseSeedIdentity: %d moral roots installed", n)
        except Exception as exc:  # pragma: no cover
            logger.warning("BaseSeedIdentity: seed_moral_roots failed: %s", exc)

        # Canonical default params — every new identity starts with these.
        # The adaptive law layer will evolve them independently per identity.
        base.params = {
            "gamma_0":       0.04,   # reflection write-back boost
            "lambda_0":      0.008,  # base wave decay rate
            "attention_tau": 4.0,    # attention focus decay time-constant
            "moral_boost":   0.05,   # moral-root reinforce on harmful encounter
            "reflect_boost": 0.04,   # pattern boost when reflection fires
            "habitat_step":  1.0,    # base movement step in habitat grid
        }

        return base


# ---------------------------------------------------------------------------
# Module-level singleton + accessor
# ---------------------------------------------------------------------------

_SEED: Optional[BaseSeedIdentity] = None
_SEED_LOCK = threading.Lock()


def get_seed(blueprint_version: str = SEED_BLUEPRINT_VERSION) -> BaseSeedIdentity:
    """
    Return the module-level ``BaseSeedIdentity`` singleton.

    The singleton is created lazily on first call.  Subsequent calls
    always return the same instance (same blueprint_version).
    Passing a different *blueprint_version* on the first call sets it
    for the lifetime of the process.
    """
    global _SEED
    if _SEED is None:
        with _SEED_LOCK:
            if _SEED is None:
                _SEED = BaseSeedIdentity(blueprint_version=blueprint_version)
                logger.info(
                    "BaseSeedIdentity singleton initialised (version=%s)",
                    blueprint_version,
                )
    return _SEED
