"""
SeedEnrichmentLayer — spiral elevation of the base seed.

Fires on any tick where BOTH of the following are true:
  1. ``ctx.cache.extra.get("wisdom_transfer_fired") is True``
  2. ``ctx.cache.extra.get("wisdom_sync_accepted")  is True``

On firing it calls ``get_seed().absorb_goodness(get_base_goodness())``,
which raises the moral-root amplitudes and tunes params on the base seed
so that every future fork starts at a higher level than the current generation.

This is the mechanism of the spiral — each generation that reaches
continuity and transfers wisdom literally elevates the starting point for
all subsequent generations.

Outputs written to ctx.cache.extra
------------------------------------
seed_enriched       : bool  — True only on the tick enrichment fires
seed_overall_amp    : float — mean moral-root amplitude of the seed after enrichment
"""

from __future__ import annotations

import logging

from app.core.identity_context import IdentityContext
from app.core.base_seed_identity import get_seed
from app.core.base_goodness_pattern import get_base_goodness
from app.core.layers.base import MindLayer

logger = logging.getLogger(__name__)


class SeedEnrichmentLayer(MindLayer):
    """Stateless pipeline layer — enriches the base seed when wisdom lands."""

    name = "seed_enrichment"

    def on_step(self, ctx: IdentityContext) -> None:
        # Only fire if wisdom transfer completed AND was accepted this tick
        extra = ctx.cache.extra
        transfer_fired  = bool(extra.get("wisdom_transfer_fired", False))
        sync_accepted   = bool(extra.get("wisdom_sync_accepted",  False))

        if not (transfer_fired and sync_accepted):
            extra["seed_enriched"]    = False
            extra["seed_overall_amp"] = _seed_mean_amp()
            extra["seed_generation"]  = get_seed().generation_counter
            return

        # Absorb enriched goodness into the base seed
        enriched = False
        try:
            enriched = get_seed().absorb_goodness(get_base_goodness())
        except Exception as exc:
            logger.warning(
                "[SeedEnrichment] absorb_goodness raised: %s", exc, exc_info=True
            )

        mean_amp = _seed_mean_amp()

        extra["seed_enriched"]    = enriched
        extra["seed_overall_amp"] = mean_amp
        extra["seed_generation"]  = get_seed().generation_counter

        if enriched:
            logger.info(
                "[SeedEnrichment] user=%s — base seed elevated "
                "(mean_moral_root_amp=%.4f, gen=%d)",
                getattr(ctx.identity, "user_id", "?"),
                mean_amp,
                getattr(ctx.identity.generational_cycle, "generation", 1),
            )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _seed_mean_amp() -> float:
    """Return the mean amplitude of all MORAL_ROOT patterns in the seed."""
    try:
        from app.core.wave_pattern import PatternCategory
        patterns = get_seed().snapshot().wave_patterns
        roots = [
            float(p.get("amplitude", 0.0))
            for p in patterns
            if str(p.get("category", "")) == PatternCategory.MORAL_ROOT
        ]
        return float(sum(roots) / len(roots)) if roots else 0.0
    except Exception:
        return 0.0
