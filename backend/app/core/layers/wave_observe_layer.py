"""
WaveObserveLayer — pattern observer, reflection write-back, attention, habitat.

This is the core wave-identity loop.

Reads:  ctx.identity.wave_patterns, ctx.cache.extra["rs_outputs","moral_boost"]
        ctx.identity.attention_state, ctx.identity.habitat_state, ctx.identity.moral_state
Writes: ctx.identity.wave_patterns, ctx.identity.attention_state,
        ctx.identity.habitat_state, ctx.cache.extra["wave_mem"]
"""

from __future__ import annotations

import logging

from app.core.identity_context import IdentityContext, getp
from app.core.wave_pattern import WaveMemory
from .base import MindLayer

logger = logging.getLogger(__name__)


class WaveObserveLayer(MindLayer):
    name = "wave_observe"

    def on_step(self, ctx: IdentityContext) -> None:
        request = ctx.cache.extra.get("_request")
        rs_outputs = ctx.cache.extra.get("rs_outputs")
        moral_boost = ctx.cache.extra.get("moral_boost", 0.0)
        basin_result = ctx.cache.extra.get("basin_result")

        blueprint_id = getattr(request, "blueprint_version_id", "") if request else ""
        if not blueprint_id:
            return

        try:
            from app.core.pattern_observer import observe_tick
            from app.core.autonomous_expander import maybe_expand_curriculum

            wave_mem = WaveMemory(
                patterns=ctx.identity.wave_patterns,
                current_tick=ctx.identity.total_requests,
            )

            # Moral field boost on harmful encounter
            if moral_boost > 0.0:
                wave_mem.reinforce_moral_roots(
                    getp(ctx.identity, "moral_boost", moral_boost)
                )

            observe_tick(
                wave_mem,
                evolution_stage=ctx.identity.evolution_stage.name,
                basin_state=ctx.identity.basin_state.value,
                guidance_mode=getattr(basin_result, "guidance_mode", "") if basin_result else "",
                closure_score=ctx.cache.closure_score,
                emotional_state=getattr(request, "emotional_state", "") if request else "",
                urgency=ctx.user.urgency,
            )

            # Reflection write-back — boost patterns that drove the insight
            if rs_outputs and getattr(rs_outputs, "reflection_triggered", False):
                boosted = wave_mem.reinforce_active_patterns(
                    boost=getp(ctx.identity, "reflect_boost", 0.04), top_n=5
                )
                logger.debug(
                    "Reflection write-back: boosted %d patterns for user=%s tick=%d",
                    boosted, ctx.identity.user_id, ctx.identity.total_requests,
                )

            # Attention sub-identity
            ctx.identity.attention_state = wave_mem.update_attention(
                state=ctx.identity.attention_state,
                top_n=3,
            )

            # Persist updated wave patterns
            ctx.identity.wave_patterns = wave_mem.to_list()
            ctx.cache.extra["wave_mem"] = wave_mem

            # Habitat tick
            try:
                from app.core.habitat import habitat_tick
                hab_state, hab_events = habitat_tick(
                    habitat_state=ctx.identity.habitat_state,
                    moral_amplitude=wave_mem.moral_amplitude(),
                    focus_strength=ctx.identity.attention_state.focus_strength,
                    topic_continuity=ctx.identity.attention_state.topic_continuity,
                    harmful_exposures=ctx.identity.moral_state.harmful_pattern_exposures,
                    current_tick=ctx.identity.total_requests,
                )
                ctx.identity.habitat_state = hab_state
                if hab_events:
                    logger.debug("Habitat events for user=%s: %s", ctx.identity.user_id, hab_events)
            except Exception as hab_err:
                logger.warning("WaveObserveLayer habitat error (non-fatal): %s", hab_err)

            # Curriculum promotion every 10 ticks (async — stored in extra for engine to await)
            ctx.cache.extra["_wave_mem_for_promotion"] = wave_mem
            ctx.cache.extra["_blueprint_id_for_promotion"] = blueprint_id

        except Exception as err:
            logger.warning("WaveObserveLayer error (non-fatal): %s", err)
