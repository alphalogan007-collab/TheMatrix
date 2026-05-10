"""
BasinStageLayer — basin classification + stage transition.

Reads:  ctx.cache.*, ctx.identity.*, ctx.cache.extra["iw_outputs","rs_outputs"]
Writes: ctx.identity.basin_state, ctx.identity.identity_probability,
        ctx.identity.evolution_stage, ctx.identity.stage_consecutive_ticks,
        ctx.identity.stage_history, ctx.cache.extra["basin_result","stage_result"]
"""

from __future__ import annotations

from app.core.identity_context import IdentityContext
from app.core.basin_classifier import classify_basin, BasinInput
from app.core.evolution_stage import EvolutionStage, StageTransitionEngine
from app.core.laws_kernel import get_spiritual_guidance, get_laws_as_guidance_directions
from .base import MindLayer

_stage_engine = StageTransitionEngine()


class BasinStageLayer(MindLayer):
    name = "basin_stage"

    def on_step(self, ctx: IdentityContext) -> None:
        iw_outputs = ctx.cache.extra.get("iw_outputs")
        rs_outputs = ctx.cache.extra.get("rs_outputs")
        iw_state = ctx.identity.internal_world
        rs_state = ctx.identity.reflective_stack

        basin_input = BasinInput(
            closure_score=ctx.cache.closure_score,
            leakage_score=ctx.cache.leakage_score,
            compatibility_score=ctx.cache.compatibility_score,
            strain_score=ctx.cache.strain_score,
            pulse_strength=ctx.user.urgency,
            internal_energy=iw_state.energy,
            internal_stress=iw_state.stress,
            prior_identity_probability=ctx.identity.identity_probability,
        )
        basin_result = classify_basin(basin_input)
        ctx.identity.basin_state = basin_result.basin_state
        ctx.identity.identity_probability = basin_result.identity_probability
        ctx.cache.extra["basin_result"] = basin_result

        stage_result = _stage_engine.step(
            stage=ctx.identity.evolution_stage,
            consecutive_ticks_at_threshold=ctx.identity.stage_consecutive_ticks,
            energy=iw_state.energy,
            stress=iw_state.stress,
            basin_state_value=basin_result.basin_state.value,
            basin_energy=basin_result.basin_energy,
            identity_probability=basin_result.identity_probability,
            experience=rs_state.experience,
            l_bm_ema=rs_state.l_bm_ema,
            l_ma_ema=rs_state.l_ma_ema,
            total_reflections=ctx.identity.total_reflections,
            closure_score=ctx.cache.closure_score,
            leakage_score=ctx.cache.leakage_score,
            total_requests=ctx.identity.total_requests,
            mean_closure_score=ctx.identity.mean_closure_score,
        )
        ctx.identity.evolution_stage = stage_result.new_stage
        ctx.identity.stage_consecutive_ticks = stage_result.consecutive_ticks_at_threshold
        if stage_result.advanced:
            ctx.identity.stage_history.append(
                f"tick {ctx.identity.total_requests}: "
                f"{stage_result.previous_stage.name} → {stage_result.new_stage.name} "
                f"({stage_result.transition_reason})"
            )
        ctx.cache.extra["stage_result"] = stage_result

        # Stage-appropriate guidance injected into InnerVoice
        extra_guidance: list = []
        if ctx.identity.evolution_stage >= EvolutionStage.BELIEF:
            extra_guidance = get_spiritual_guidance()
        elif ctx.identity.evolution_stage >= EvolutionStage.MEMORY:
            extra_guidance = get_laws_as_guidance_directions()[:5]
        ctx.cache.extra["stage_guidance"] = extra_guidance
