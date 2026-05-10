"""
ResidualRealityLayer — residual novelty + reality-check kernel.

Reads:  ctx.cache.extra["sensory_biases"], ctx.cache.extra["_request"]
Writes: ctx.cache.residual_score, ctx.cache.manipulation_signals,
        ctx.cache.reality_verdicts, ctx.cache.reality_score
"""

from __future__ import annotations

from app.core.identity_context import IdentityContext
from .base import MindLayer


class ResidualRealityLayer(MindLayer):
    name = "residual_reality"

    def on_step(self, ctx: IdentityContext) -> None:
        from app.core.residual_novelty import ResidualNoveltyInput, compute_residual_novelty
        from app.core.reality_check_kernel import run_reality_check_kernel

        request = ctx.cache.extra.get("_request")
        biases = ctx.cache.extra.get("sensory_biases", {})
        novelty_bias = ctx.cache.extra.get("sensory_novelty_bias", 0.0)

        residual_input = ResidualNoveltyInput(
            novelty_score=float(min(1.0, max(0.0, 0.40 + novelty_bias * 0.3))),
            contradiction_with_memory=0.20,
            unresolved_context=0.30 if (request and not request.situation_summary) else 0.10,
            source_gap=0.20,
        )
        residual = compute_residual_novelty(residual_input)
        ctx.cache.residual_score = residual.residual_score
        ctx.cache.extra["residual"] = residual

        claims = (request.detected_claims or []) if request else []
        reality_results = [run_reality_check_kernel(claim) for claim in claims[:3]]
        ctx.cache.manipulation_signals = [sig for r in reality_results for sig in r.manipulation_signals]
        ctx.cache.reality_verdicts = [f"{r.claim[:60]}... → {r.verdict.value}" for r in reality_results]
        ctx.cache.reality_score = (
            sum(r.confidence for r in reality_results) / len(reality_results)
            if reality_results else 0.70
        )
