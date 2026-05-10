"""
OscillationLayer -- per-identity phase dynamics and inside/outside boundary.

Pipeline slot: after GlobalCouplerLayer, before BeliefLayer.

The Pair Law in action
----------------------
Every identity is an inside/outside pair with oscillation across the boundary.

  inner_pressure = how much the identity is "full" -- unresolved thoughts,
                   contradiction pressure, subconscious queue depth.
                   High inner_pressure -> strong emission/radiation.

  outer_pressure = how much external input is pressing inward.
                   High outer_pressure -> boundary disturbed, high reception.

  boundary_flux  = |inner - outer| -- drives the exchange loop.
                   High flux -> active exchange tick.
                   Low flux  -> equilibrium, consolidation tick.

Per-tick logic
--------------
1. PHASE ADVANCE
   theta += natural_frequency  (+entrainment correction from GlobalCoupler)
   theta = theta % (2 * pi)

2. INNER PRESSURE
   Derived from:
     - subconscious thought_queue depth (normalised)
     - contradiction_score from BeliefState
     - ctx.cache.residual_score (unresolved pattern pressure)
   inner_pressure is the "emission pressure" -- how much the identity wants
   to radiate outward.

3. OUTER PRESSURE
   Derived from:
     - user urgency
     - user novelty
     - sensory_novelty_bias (from SensoryLayer)
   outer_pressure is the "reception pressure" -- how much the boundary
   is disturbed by incoming input.

4. BOUNDARY FLUX
   flux = |inner_pressure - outer_pressure|
   Extreme flux is clamped.  The oscillation loop is healthiest near 0.5.

5. PULSE AMPLITUDE
   EMA over decayed mean wave amplitude.  Tracks the actual field energy.

6. ENTRAINMENT
   When GlobalCouplerState.awareness_emerged, the phase locks toward
   global_synchrony phase (K * sin(theta_global - theta) Kuramoto step).

7. EMISSION / RECEPTION STRENGTHS
   emission  = pulse_amplitude * inner_pressure
   reception = 1 - entrainment_strength * 0.5

8. PUBLISH
   ctx.cache.extra["oscillation_phase"]
   ctx.cache.extra["boundary_flux"]
   ctx.cache.extra["inner_pressure"]
   ctx.cache.extra["outer_pressure"]
   ctx.cache.extra["emission_strength"]
   ctx.cache.extra["reception_strength"]

Tunable params (via getp):
  osc_natural_frequency  = 0.10  ticks^-1 intrinsic rhythm
  osc_entrainment_k      = 0.20  Kuramoto coupling to global synchrony
  osc_pressure_tau       = 0.30  EMA smoothing for pressures
  osc_amp_tau            = 0.20  EMA smoothing for pulse_amplitude
"""
from __future__ import annotations

import logging
import math

from app.core.identity_context import IdentityContext, getp
from app.core.oscillation import OscillationState
from .base import MindLayer

logger = logging.getLogger(__name__)

TWO_PI = 2.0 * math.pi


class OscillationLayer(MindLayer):
    name = "oscillation"

    def on_step(self, ctx: IdentityContext) -> None:
        try:
            self._run(ctx)
        except Exception as err:
            logger.warning("OscillationLayer error (non-fatal): %s", err)

    def _run(self, ctx: IdentityContext) -> None:
        from app.core.wave_pattern import WaveMemory

        identity = ctx.identity
        tick     = identity.total_requests
        osc: OscillationState = identity.oscillation_state

        # -- Tunable params
        nat_freq  = getp(identity, "osc_natural_frequency", 0.10)
        k_entrain = getp(identity, "osc_entrainment_k",     0.20)
        p_tau     = getp(identity, "osc_pressure_tau",      0.30)
        amp_tau   = getp(identity, "osc_amp_tau",           0.20)

        # -- 1. Phase advance with optional entrainment correction
        sync = identity.coupler_state.global_synchrony
        if identity.coupler_state.awareness_emerged and sync > 0.5:
            # Kuramoto: dθ/dt = ω₀ + K * r * sin(θ_global - θ)
            # Use synchrony as proxy for mean-field phase (all patterns in sync)
            theta_global = osc.phase + math.pi * (1.0 - sync)  # approx
            entrain_delta = k_entrain * sync * math.sin(theta_global - osc.phase)
            osc.entrainment_strength = min(1.0, sync * 1.2)
        else:
            entrain_delta = 0.0
            osc.entrainment_strength = max(0.0, osc.entrainment_strength * 0.90)

        osc.phase = (osc.phase + nat_freq + entrain_delta) % TWO_PI
        osc.total_cycles = osc.phase / TWO_PI + (osc.total_cycles - osc.total_cycles % 1)

        # -- 2. Inner pressure (emission driver)
        queue_depth = min(1.0, len(identity.thought_queue) / 20.0)
        contradiction = identity.belief_state.contradiction_score
        residual      = ctx.cache.residual_score
        target_inner  = min(1.0,
            0.40 * queue_depth
            + 0.35 * contradiction
            + 0.25 * residual
        )
        osc.inner_pressure = (
            osc.inner_pressure * (1.0 - p_tau) + target_inner * p_tau
        )

        # -- 3. Outer pressure (reception driver)
        urgency     = ctx.user.urgency
        novelty     = ctx.user.novelty
        sensory_nov = float(ctx.cache.extra.get("sensory_novelty_bias", 0.0))
        target_outer = min(1.0,
            0.50 * urgency
            + 0.30 * novelty
            + 0.20 * sensory_nov
        )
        osc.outer_pressure = (
            osc.outer_pressure * (1.0 - p_tau) + target_outer * p_tau
        )

        # -- 4. Boundary flux
        osc.boundary_flux = abs(osc.inner_pressure - osc.outer_pressure)

        # -- 5. Pulse amplitude (EMA over mean wave field)
        wave_mem  = WaveMemory(patterns=identity.wave_patterns, current_tick=tick)
        amps      = [p.decayed_amplitude(tick) for p in wave_mem._patterns]
        mean_amp  = (sum(amps) / len(amps)) if amps else 0.0
        osc.pulse_amplitude = (
            osc.pulse_amplitude * (1.0 - amp_tau) + mean_amp * amp_tau
        )

        # -- 6. Derive emission / reception
        osc.emission_strength  = float(osc.pulse_amplitude * osc.inner_pressure)
        osc.reception_strength = float(1.0 - osc.entrainment_strength * 0.50)

        osc.last_tick = tick

        # -- 7. Publish
        ctx.cache.extra["oscillation_phase"]    = round(osc.phase, 4)
        ctx.cache.extra["boundary_flux"]        = round(osc.boundary_flux, 4)
        ctx.cache.extra["inner_pressure"]       = round(osc.inner_pressure, 4)
        ctx.cache.extra["outer_pressure"]       = round(osc.outer_pressure, 4)
        ctx.cache.extra["emission_strength"]    = round(osc.emission_strength, 4)
        ctx.cache.extra["reception_strength"]   = round(osc.reception_strength, 4)
        ctx.cache.extra["entrainment_strength"] = round(osc.entrainment_strength, 4)

        logger.debug(
            "OscillationLayer: user=%s tick=%d phase=%.3f flux=%.3f "
            "emit=%.3f recv=%.3f entrain=%.3f",
            identity.user_id, tick, osc.phase, osc.boundary_flux,
            osc.emission_strength, osc.reception_strength, osc.entrainment_strength,
        )
