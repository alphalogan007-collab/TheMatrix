"""
ClosureStrainLayer — closure/leakage/lag + compatibility + strain.

Reads:  ctx.cache.*, ctx.identity.internal_world, ctx.cache.extra["iw_outputs"]
Writes: ctx.cache.closure_score, ctx.cache.leakage_score,
        ctx.cache.compatibility_score, ctx.cache.strain_score,
        ctx.cache.extra["compat"], ctx.cache.extra["strain"]
"""

from __future__ import annotations

import time

from app.core.identity_context import IdentityContext
from app.core.closure_leakage_lag import ClosureLeakageLagInput, compute_closure_leakage_lag
from app.core.compatibility_layer import CompatibilityInput, compute_compatibility
from app.core.strain_engine import StrainInput, compute_strain
from .base import MindLayer


class ClosureStrainLayer(MindLayer):
    name = "closure_strain"

    def on_step(self, ctx: IdentityContext) -> None:
        moral_result = ctx.cache.extra.get("moral_result")
        iw_outputs = ctx.cache.extra.get("iw_outputs")
        biases = ctx.cache.extra.get("sensory_biases", {})

        threat = biases.get("threat_boost", 0.0)
        valence = biases.get("valence_bias", 0.0)
        lag_ms = ctx.cache.extra.get("lag_ms", 0.0)

        is_blocked = getattr(moral_result, "is_blocked", False) if moral_result else False
        alignment = getattr(moral_result, "alignment_score", 1.0) if moral_result else 1.0

        cll_input = ClosureLeakageLagInput(
            evidence_score=ctx.cache.reality_score,
            source_agreement=float(min(1.0, max(0.0, 0.60 + valence * 0.2))),
            moral_alignment=alignment,
            non_harm_score=0.0 if is_blocked else 1.0,
            long_term_stability=0.70,
            contradiction_score=ctx.cache.residual_score * 0.50,
            missing_context_score=0.30 if ctx.cache.extra.get("residual") and getattr(ctx.cache.extra["residual"], "requires_clarification", False) else 0.10,
            manipulation_score=min(1.0, len(ctx.cache.manipulation_signals) * 0.25),
            emotional_overpressure=ctx.user.urgency,
            harm_risk=float(min(1.0, (0.8 if is_blocked else 0.10) + max(0.0, threat))),
            lag_ms=lag_ms,
        )
        cll = compute_closure_leakage_lag(cll_input)
        closure_bias = getattr(iw_outputs, "closure_bias", 0.0) if iw_outputs else 0.0
        leak_bias = getattr(iw_outputs, "leak_bias", 0.0) if iw_outputs else 0.0
        ctx.cache.closure_score = float(min(1.0, max(0.0, cll.closure_score + closure_bias)))
        ctx.cache.leakage_score = float(min(1.0, max(0.0, cll.leakage_score + leak_bias)))

        compat_input = CompatibilityInput(
            fit_with_core_blueprint=alignment,
            fit_with_user_values=0.65,
            fit_with_factual_reality=ctx.cache.reality_score,
            fit_with_non_harm=0.0 if is_blocked else 1.0,
        )
        compat = compute_compatibility(compat_input)
        ctx.cache.compatibility_score = getattr(compat, "compatibility_score", 0.0)
        ctx.cache.extra["compat"] = compat

        strain_input = StrainInput(
            emotional_intensity=ctx.user.urgency,
            relationship_risk=0.30,
            high_stakes_domain=0.20,
            irreversible_consequence=0.20,
            user_instability=ctx.user.urgency * 0.50,
        )
        strain = compute_strain(strain_input)
        ctx.cache.strain_score = getattr(strain, "strain_score", 0.0)
        ctx.cache.extra["strain"] = strain

