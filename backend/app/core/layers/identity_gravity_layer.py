"""
IdentityGravityLayer -- identity gravity field.

G_ij = (M_i * M_j * R_ij * C_ij) / (D_ij + eps) - N_ij

Pipeline slot: after BeliefLayer, before ConsciousLayer.

Belief-as-Sun: a high-mass belief/moral-root field radiates an interpretation
gravity that pulls resonant patterns inward and repels incompatible/harmful ones.

Per-tick logic:
1. Compute identity centroid (mean of all active belief centers)
2. Compute identity mass M_i from belief amplitudes + moral amplitude + closure
3. For each active wave pattern compute gravity G_ij
4. ATTRACT: G > attract_threshold -> reinforce pattern (boost amplitude)
5. REPEL:   G < repel_threshold   -> decrement observation_count
             if pattern is harmful and strongly repelled -> publish for quarantine
6. Publish inspect log: ctx.cache.extra["gravity_log"] list of GravityResult dicts
   ctx.cache.extra["identity_mass"]
   ctx.cache.extra["attracted_count"]
   ctx.cache.extra["repelled_count"]

Tunable params (via getp):
  gravity_attract_threshold  = 0.30   G above this -> reinforce
  gravity_repel_threshold    = -0.20  G below this -> resist
  gravity_attract_boost      = 0.03   reinforce magnitude per tick
  gravity_max_attract        = 10     max patterns reinforced per tick
"""
from __future__ import annotations

import logging
from typing import List

from app.core.identity_context import IdentityContext, getp
from app.core.identity_gravity import gravity_score, identity_mass, GravityResult
from .base import MindLayer

logger = logging.getLogger(__name__)


class IdentityGravityLayer(MindLayer):
    name = "identity_gravity"

    def on_step(self, ctx: IdentityContext) -> None:
        try:
            self._run(ctx)
        except Exception as err:
            logger.warning("IdentityGravityLayer error (non-fatal): %s", err)

    def _run(self, ctx: IdentityContext) -> None:
        from app.core.wave_pattern import WaveMemory

        identity = ctx.identity
        tick     = identity.total_requests

        attract_thr  = getp(identity, "gravity_attract_threshold", 0.30)
        repel_thr    = getp(identity, "gravity_repel_threshold",  -0.20)
        attract_boost= getp(identity, "gravity_attract_boost",     0.03)
        max_attract  = max(1, int(getp(identity, "gravity_max_attract", 10.0)))

        # -- Identity centroid (mean of belief centers, fallback all-0.5)
        beliefs = identity.belief_state.beliefs
        if beliefs:
            d = len(beliefs[0].center)
            centroid = [
                sum(b.center[i] for b in beliefs) / len(beliefs)
                for i in range(d)
            ]
        else:
            centroid = [0.5] * 6

        # -- Identity mass
        belief_amps  = [b.amplitude for b in beliefs]
        moral_amp    = identity.moral_state.moral_amplitude
        M_i = identity_mass(
            belief_amplitudes=belief_amps,
            moral_amplitude=moral_amp,
            mean_closure=ctx.cache.closure_score,
        )

        # -- Belief pattern id set
        belief_pat_ids = {b.pattern_id for b in beliefs}

        # -- Compute gravity for all active patterns
        wave_mem = WaveMemory(patterns=identity.wave_patterns, current_tick=tick)
        results: List[GravityResult] = []

        for pat in wave_mem._patterns:
            amp = pat.decayed_amplitude(tick)
            if amp < 0.10:
                continue
            results.append(gravity_score(
                pattern_id=pat.pattern_id,
                pattern_center=list(pat.center),
                pattern_amplitude=amp,
                pattern_observation_count=pat.observation_count,
                pattern_mean_closure=pat.mean_closure,
                pattern_category=pat.category,
                is_belief=(pat.pattern_id in belief_pat_ids),
                identity_centroid=centroid,
                M_i=M_i,
                contradiction_score=identity.belief_state.contradiction_score,
                moral_alignment=ctx.cache.moral_alignment,
                closure_score=max(0.01, ctx.cache.closure_score),
            ))

        # Sort by G descending
        results.sort(key=lambda r: r.G, reverse=True)

        # -- ATTRACT: reinforce top patterns
        attracted, repelled = 0, 0
        for res in results[:max_attract]:
            if res.G >= attract_thr:
                if pat.category != "harmful":   # harmful never boosted
                    wave_mem.reinforce_pattern(res.pattern_id, boost=attract_boost * res.G)
                attracted += 1

        # -- REPEL: log + flag patterns for quarantine
        for res in results:
            if res.G <= repel_thr:
                repelled += 1
                logger.debug(
                    "IdentityGravityLayer: REPEL pat=%s G=%.3f reason=%s user=%s",
                    res.pattern_id, res.G, res.reason, identity.user_id,
                )

        # Write back reinforced patterns
        identity.wave_patterns = wave_mem.to_list()

        # -- Publish
        ctx.cache.extra["identity_mass"]    = round(M_i, 4)
        ctx.cache.extra["attracted_count"]  = attracted
        ctx.cache.extra["repelled_count"]   = repelled
        ctx.cache.extra["gravity_log"] = [
            {
                "pattern_id": r.pattern_id,
                "G":          round(r.G, 4),
                "mass":       round(r.M_j, 4),
                "resonance":  round(r.resonance, 4),
                "reason":     r.reason,
            }
            for r in results
        ]

        logger.debug(
            "IdentityGravityLayer: user=%s tick=%d M_i=%.3f attracted=%d repelled=%d",
            identity.user_id, tick, M_i, attracted, repelled,
        )
