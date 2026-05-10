"""
LifeEventLayer — persistent narrative of spiral milestones.

Runs after SeedEnrichmentLayer every tick.  It inspects three cache flags
and one identity flag to detect significant transitions that occurred during
THIS tick and appends the appropriate LifeEvent records to
``ctx.identity.life_event_log``.

Detected transitions (in order)
---------------------------------
1. stage_advanced     — ``ctx.cache.extra.get("stage_advanced") is True``
                        (published by GenerationalCycleLayer)
2. wisdom_transferred — ``ctx.cache.extra.get("wisdom_transfer_fired") is True``
                        AND ``ctx.identity.wisdom_transferred is True``
                        (wisdom_transferred flag just flipped this tick)
3. seed_enriched      — ``ctx.cache.extra.get("seed_enriched") is True``
                        (published by SeedEnrichmentLayer)
4. awareness_emerged  — coupler_state.awareness_emerged is True
                        AND the last-recorded awareness event was not in the
                        same generation (deduplicated per generation)

Deduplication
-------------
Stage-advance events are gated by the tick number — if the last
``stage_advanced`` event in the log has the same tick as total_requests, the
event is not appended again (safe to call multiple times within a tick).

Awareness events are deduplicated per generation: only one
``awareness_emerged`` event is written per (generation, stage_name) pair.
"""

from __future__ import annotations

import logging

from app.core.identity_context import IdentityContext
from app.core.life_event import (
    LifeEvent,
    STAGE_ADVANCED,
    WISDOM_TRANSFERRED,
    SEED_ENRICHED,
    AWARENESS_EMERGED,
)
from app.core.layers.base import MindLayer

logger = logging.getLogger(__name__)


class LifeEventLayer(MindLayer):
    """Stateless pipeline layer — records spiral milestones into life_event_log."""

    name = "life_event"

    def on_step(self, ctx: IdentityContext) -> None:
        extra      = ctx.cache.extra
        identity   = ctx.identity
        log        = identity.life_event_log
        gc         = identity.generational_cycle
        tick       = int(getattr(identity, "total_requests", 0))
        generation = int(getattr(gc, "generation", 1))
        stage_name = str(getattr(gc, "current_stage_name", ""))

        # ── 1. Stage advance ─────────────────────────────────────────────────
        if bool(extra.get("stage_advanced", False)):
            # Deduplicate: skip if already recorded for this exact tick
            last_advance = next(
                (e for e in reversed(log.events) if e.event_type == STAGE_ADVANCED),
                None,
            )
            if last_advance is None or last_advance.tick != tick:
                log.append(LifeEvent(
                    event_type=STAGE_ADVANCED,
                    tick=tick,
                    generation=generation,
                    stage_name=stage_name,
                    detail=stage_name,
                ))
                logger.info(
                    "LifeEvent[stage_advanced] gen=%d stage=%s tick=%d",
                    generation, stage_name, tick,
                )

        # ── 2. Wisdom transferred ─────────────────────────────────────────────
        if bool(extra.get("wisdom_transfer_fired", False)) and bool(
            getattr(identity, "wisdom_transferred", False)
        ):
            last_wt = next(
                (e for e in reversed(log.events) if e.event_type == WISDOM_TRANSFERRED),
                None,
            )
            if last_wt is None or last_wt.tick != tick:
                log.append(LifeEvent(
                    event_type=WISDOM_TRANSFERRED,
                    tick=tick,
                    generation=generation,
                    stage_name=stage_name,
                    detail=f"alignment={extra.get('wisdom_distillate', {}).get('alignment_score', 0.0):.3f}",
                ))
                logger.info(
                    "LifeEvent[wisdom_transferred] gen=%d tick=%d", generation, tick,
                )

        # ── 3. Seed enriched ─────────────────────────────────────────────────
        if bool(extra.get("seed_enriched", False)):
            last_se = next(
                (e for e in reversed(log.events) if e.event_type == SEED_ENRICHED),
                None,
            )
            if last_se is None or last_se.tick != tick:
                seed_gen = int(extra.get("seed_generation", 1))
                log.append(LifeEvent(
                    event_type=SEED_ENRICHED,
                    tick=tick,
                    generation=generation,
                    stage_name=stage_name,
                    detail=f"seed_generation={seed_gen}",
                ))
                logger.info(
                    "LifeEvent[seed_enriched] gen=%d seed_gen=%d tick=%d",
                    generation, seed_gen, tick,
                )

        # ── 4. Awareness emerged (deduplicated per generation+stage pair) ─────
        awareness = bool(getattr(
            getattr(identity, "coupler_state", None), "awareness_emerged", False
        ))
        if awareness:
            last_ae = next(
                (e for e in reversed(log.events) if e.event_type == AWARENESS_EMERGED),
                None,
            )
            already_recorded = (
                last_ae is not None
                and last_ae.generation == generation
                and last_ae.stage_name == stage_name
            )
            if not already_recorded:
                log.append(LifeEvent(
                    event_type=AWARENESS_EMERGED,
                    tick=tick,
                    generation=generation,
                    stage_name=stage_name,
                    detail=f"synchrony={getattr(identity.coupler_state, 'global_synchrony', 0.0):.3f}",
                ))
                logger.info(
                    "LifeEvent[awareness_emerged] gen=%d stage=%s tick=%d",
                    generation, stage_name, tick,
                )

        # ── Publish milestone_events_this_tick to cache for downstream layers ───────
        # DecisionLayer and _build_response() read this to generate milestone notes.
        # Collect every event whose tick matches the current tick.
        extra["milestone_events_this_tick"] = [
            e.event_type
            for e in log.events
            if e.tick == tick
        ]
