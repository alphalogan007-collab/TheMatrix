"""
DecisionLayer — stability band + inner voice + candidate scoring.

Reads:  ctx.cache.*, ctx.identity.*, ctx.cache.extra["basin_result","strain","compat",
        "rs_outputs","iw_outputs","stage_guidance"]
Writes: ctx.cache.recommended_direction, ctx.cache.extra["band_result","inner_voice","selected"]
"""

from __future__ import annotations

from app.core.identity_context import IdentityContext
from app.core.stability_band import StabilityBandInput, classify_stability_band
from app.core.inner_voice_layer import InnerVoiceContext, run_inner_voice_layer
from app.core.advice_selector import AdviceCandidate, select_best_advice
from .base import MindLayer


class DecisionLayer(MindLayer):
    name = "decision"

    def on_step(self, ctx: IdentityContext) -> None:
        request = ctx.cache.extra.get("_request")
        moral_result = ctx.cache.extra.get("moral_result")
        rs_outputs = ctx.cache.extra.get("rs_outputs")
        iw_outputs = ctx.cache.extra.get("iw_outputs")
        basin_result = ctx.cache.extra.get("basin_result")
        strain = ctx.cache.extra.get("strain")
        compat = ctx.cache.extra.get("compat")
        residual = ctx.cache.extra.get("residual")

        is_blocked = getattr(moral_result, "is_blocked", False) if moral_result else False
        alignment = getattr(moral_result, "alignment_score", 1.0) if moral_result else 1.0
        correction_note = getattr(moral_result, "correction_note", "") if moral_result else ""

        band_input = StabilityBandInput(
            emotional_intensity=ctx.user.urgency,
            confusion_score=ctx.cache.residual_score,
            harm_risk_score=0.8 if is_blocked else 0.0,
            manipulation_score=min(1.0, len(ctx.cache.manipulation_signals) * 0.25),
            urgency=ctx.user.urgency,
            coherence_score=1.0 - ctx.cache.residual_score,
        )
        band_result = classify_stability_band(band_input)
        ctx.cache.extra["band_result"] = band_result

        iv_ctx = InnerVoiceContext(
            emotional_intensity=ctx.user.urgency,
            confusion_score=ctx.cache.residual_score,
            harm_risk_score=0.8 if is_blocked else 0.0,
            manipulation_score=min(1.0, len(ctx.cache.manipulation_signals) * 0.25),
            moral_alignment=alignment,
            factual_alignment=ctx.cache.reality_score,
            non_harm_alignment=0.0 if is_blocked else 1.0,
            reality_check_alignment=ctx.cache.reality_score,
            blueprint_version_id=getattr(request, "blueprint_version_id", "") if request else "",
            blueprint_checksum=getattr(request, "blueprint_checksum", "") if request else "",
            stability_band=band_result,
            closure_score=ctx.cache.closure_score,
            leakage_score=ctx.cache.leakage_score,
        )
        inner_voice = run_inner_voice_layer(iv_ctx)
        ctx.cache.recommended_direction = getattr(inner_voice, "recommended_direction", "")
        ctx.cache.extra["inner_voice"] = inner_voice

        # Build candidates
        action_bias = getattr(iw_outputs, "action_bias", 0.0) if iw_outputs else 0.0
        direction = ctx.cache.recommended_direction
        basin_note = getattr(basin_result, "guidance_mode", "") if basin_result else ""
        reflection_note = getattr(rs_outputs, "reflection_summary", "") if rs_outputs else ""

        if is_blocked:
            content = (
                "The Core Blueprint cannot guide in the requested direction as it conflicts "
                "with non-harm and moral constraints. "
                "Please consult a qualified professional for this type of situation."
            )
            if correction_note:
                content += f" {correction_note}"
        else:
            content = (
                f"Based on available evidence and your current state: {direction} "
                "The Core Blueprint recommends a stable, grounded approach that prioritises "
                "long-term wellbeing over short-term relief."
            )
            if basin_note:
                content += f" [{basin_note}]"
            if reflection_note:
                content += f" {reflection_note}"
            if action_bias > 0.05:
                content += " Your current energy supports taking a clear, decisive step."
            elif action_bias < -0.05:
                content += " Your current state calls for rest and consolidation before acting."

        candidates = [AdviceCandidate(
            content=content,
            closure_score=ctx.cache.closure_score,
            leakage_score=ctx.cache.leakage_score,
            strain_penalty=getattr(strain, "penalty", 0.0) if strain else 0.0,
            compatibility_bonus=getattr(compat, "bonus", 0.0) if compat else 0.0,
            reality_check_bonus=0.10,
            moral_alignment=alignment,
            is_blocked=is_blocked,
        )]
        ctx.cache.extra["selected"] = select_best_advice(candidates)
