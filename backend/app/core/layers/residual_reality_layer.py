"""ResidualRealityLayer — residual novelty + manipulation detection.

Reads:  ctx.cache.extra["sensory_novelty_bias"], ctx.cache.extra["_request"]
Writes: ctx.cache.residual_score, ctx.cache.manipulation_signals,
        ctx.cache.reality_verdicts, ctx.cache.reality_score

Y Theory:
  residual = what the mind has not yet absorbed.
  novelty_bias (from SensoryLayer) is the mismatch signal — how unexpected the
  input is relative to known patterns. residual_from_resonance(1 - novelty_bias)
  maps this directly: high novelty -> high residual -> less coherence absorbed.

  reality_score is set to a neutral baseline (0.70). The mind has no truth
  oracle — it cannot score the factual accuracy of user claims. What it CAN
  detect are manipulation signals (see reality_check_kernel).
"""

from __future__ import annotations

from app.core.identity_context import IdentityContext
from .base import MindLayer


class ResidualRealityLayer(MindLayer):
    name = "residual_reality"

    def on_step(self, ctx: IdentityContext) -> None:
        from app.core.residual_novelty import residual_from_resonance
        from app.core.reality_check_kernel import run_reality_check_kernel

        request = ctx.cache.extra.get("_request")
        novelty_bias = ctx.cache.extra.get("sensory_novelty_bias", 0.0)

        # Residual = 1 - resonance. novelty_bias IS the novelty/mismatch measure.
        # A perfectly known input (novelty=0) -> full resonance -> residual=0.
        # A completely unknown input (novelty=1) -> no resonance -> residual=1.
        resonance_proxy = max(0.0, min(1.0, 1.0 - novelty_bias))
        residual = residual_from_resonance(resonance_proxy)
        ctx.cache.residual_score = residual.residual_score
        ctx.cache.extra["residual"] = residual

        # Scan detected claims for manipulation signals only
        claims = (request.detected_claims or []) if request else []
        reality_results = [run_reality_check_kernel(claim) for claim in claims[:3]]
        ctx.cache.manipulation_signals = [
            sig for r in reality_results for sig in r.manipulation_signals
        ]
        # No truth verdicts — the mind does not evaluate claim truthfulness
        ctx.cache.reality_verdicts = []
        # Neutral baseline — not a real score, placeholder for pipeline compat
        ctx.cache.reality_score = 0.70
