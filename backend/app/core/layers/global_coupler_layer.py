"""
GlobalCouplerLayer — Kuramoto phase synchrony over active wave patterns.

Ported from existence_lab layers/global_coupler_layer.py with MindAI
adaptations:
  - "entities" = top-N active wave patterns (by decayed amplitude)
  - phases stored in ctx.identity.coupler_state.pattern_phases (not on the
    pattern itself — state never lives in the pattern object)
  - natural frequency ωⱼ derived from category (moral_root slowest, noise fastest)
  - pulse_global proxy = ctx.cache.closure_score (coherence of the current tick)
  - identity_continuity proxy = ctx.identity.attention_state.topic_continuity
  - On awareness_emerged: reinforce participating patterns via WaveMemory

Reads:  ctx.identity.wave_patterns, ctx.identity.coupler_state,
        ctx.identity.attention_state.topic_continuity,
        ctx.cache.closure_score, ctx.identity.total_requests
Writes: ctx.identity.coupler_state (all fields),
        ctx.identity.wave_patterns (reinforcement on awareness),
        ctx.cache.extra["global_synchrony"],
        ctx.cache.extra["awareness_emerged"]

Tunable params (all via getp):
  coupler_k                   = 0.06   Kuramoto coupling strength
  coupler_awareness_threshold = 0.70   synchrony must exceed this
  coupler_identity_cont_thr   = 0.45   topic_continuity floor
  coupler_awareness_cont_thr  = 0.35   awareness_continuity floor
  coupler_pulse_threshold     = 0.10   closure_score floor
  coupler_min_patterns        = 4      minimum active patterns
  coupler_dwell_ticks         = 2      gate must stay open N ticks
  coupler_dt                  = 1.0    Euler step size
  coupler_top_n               = 8      patterns to couple
  coupler_reinforce_boost     = 0.02   per-tick boost when aware
"""

from __future__ import annotations

import logging
import math
from typing import List, Tuple

from app.core.identity_context import IdentityContext, getp
from app.core.global_coupler import GlobalCouplerState
from .base import MindLayer

logger = logging.getLogger(__name__)

# Natural frequency per category (rad / tick) — moral_root slowest, noise fastest
_CATEGORY_FREQ = {
    "moral_root":   0.05,
    "stable_truth": 0.10,
    "knowledge":    0.20,
    "noise":        0.40,
    "harmful":      0.50,
}
_DEFAULT_FREQ = 0.20


class GlobalCouplerLayer(MindLayer):
    name = "global_coupler"

    def on_reset(self, ctx: IdentityContext) -> None:
        # Ensure cache keys exist before other layers might read them
        ctx.cache.extra.setdefault("global_synchrony", 0.0)
        ctx.cache.extra.setdefault("awareness_emerged", False)

    def on_step(self, ctx: IdentityContext) -> None:
        try:
            self._run(ctx)
        except Exception as err:
            logger.warning("GlobalCouplerLayer error (non-fatal): %s", err)
            ctx.cache.extra["global_synchrony"] = 0.0
            ctx.cache.extra["awareness_emerged"] = False

    def _run(self, ctx: IdentityContext) -> None:
        import numpy as np
        from app.core.wave_pattern import WaveMemory

        identity = ctx.identity
        state: GlobalCouplerState = identity.coupler_state
        tick = identity.total_requests

        # ── Tunable params ──────────────────────────────────────────────────
        k = getp(identity, "coupler_k", 0.06)
        sync_thr   = getp(identity, "coupler_awareness_threshold",   0.70)
        id_cont_thr = getp(identity, "coupler_identity_cont_thr",    0.45)
        aw_cont_thr = getp(identity, "coupler_awareness_cont_thr",   0.35)
        pulse_thr   = getp(identity, "coupler_pulse_threshold",      0.10)
        min_pats    = int(getp(identity, "coupler_min_patterns",     4.0))
        dwell       = max(1, int(getp(identity, "coupler_dwell_ticks", 2.0)))
        dt          = getp(identity, "coupler_dt",                   1.0)
        top_n       = max(2, int(getp(identity, "coupler_top_n",     8.0)))
        boost       = getp(identity, "coupler_reinforce_boost",      0.02)

        # ── Select top-N active patterns ────────────────────────────────────
        wave_mem = WaveMemory(patterns=identity.wave_patterns, current_tick=tick)
        active = _top_patterns(wave_mem, top_n, tick)
        n = len(active)

        if n < 2:
            state.global_synchrony = 0.0
            ctx.cache.extra["global_synchrony"] = 0.0
            ctx.cache.extra["awareness_emerged"] = state.awareness_emerged
            state.last_tick = tick
            return

        # ── Initialise / fetch phases ────────────────────────────────────────
        phases: List[float] = []
        pat_ids: List[str] = []
        freqs:  List[float] = []
        for pat_id, amp, cat in active:
            # Seed phase from amplitude on first encounter
            if pat_id not in state.pattern_phases:
                state.pattern_phases[pat_id] = float(amp * 2.0 * math.pi)
            phases.append(state.pattern_phases[pat_id])
            pat_ids.append(pat_id)
            freqs.append(_CATEGORY_FREQ.get(cat, _DEFAULT_FREQ))

        # ── Kuramoto coupling step ───────────────────────────────────────────
        phases_arr = np.asarray(phases, dtype=float)
        new_phases = phases_arr.copy()
        for i in range(n):
            coupling_sum = float(np.sum(np.sin(phases_arr - phases_arr[i])))
            drive = k * coupling_sum / max(1, n - 1)
            new_phases[i] = phases_arr[i] + dt * (freqs[i] + drive)

        # Write back updated phases
        for pat_id, theta in zip(pat_ids, new_phases.tolist()):
            state.pattern_phases[pat_id] = float(theta)

        # Prune phases for patterns that are no longer in wave_patterns
        live_ids = {p["pattern_id"] for p in identity.wave_patterns}
        state.pattern_phases = {k: v for k, v in state.pattern_phases.items() if k in live_ids}

        # ── Global synchrony r(t) = |mean(e^{iθ})| ─────────────────────────
        complex_order = float(np.abs(np.mean(np.exp(1j * new_phases))))
        synchrony = float(np.clip(complex_order, 0.0, 1.0))
        state.global_synchrony = synchrony

        # ── Awareness gate ───────────────────────────────────────────────────
        # Proxies for existence_lab fields:
        #   identity_continuity  = topic_continuity (attention sub-identity)
        #   pulse_global         = closure_score    (coherence this tick)
        id_cont = float(np.clip(identity.attention_state.topic_continuity, 0.0, 1.0))
        aw_cont_prev = float(np.clip(state.awareness_continuity, 0.0, 1.0))
        pulse_global = float(np.clip(ctx.cache.closure_score, 0.0, 1.0))

        gate_open = bool(
            synchrony    >= sync_thr
            and n        >= max(1, min_pats)
            and id_cont  >= id_cont_thr
            and aw_cont_prev >= aw_cont_thr
            and pulse_global >= pulse_thr
        )

        state.awareness_gate_streak = (state.awareness_gate_streak + 1) if gate_open else 0
        awareness_emerged = bool(state.awareness_gate_streak >= dwell)
        state.awareness_emerged = awareness_emerged

        # ── Continuity update ────────────────────────────────────────────────
        aw_cont_new = float(np.clip(max(aw_cont_prev, synchrony), 0.0, 1.0))
        aw_cont_new = float(min(aw_cont_new, id_cont))
        self_aw_cont = float(np.clip(state.self_awareness_continuity, 0.0, 1.0))
        self_aw_cont = float(min(self_aw_cont, aw_cont_new))

        state.identity_continuity = id_cont
        state.awareness_continuity = aw_cont_new
        state.self_awareness_continuity = self_aw_cont
        state.last_tick = tick

        # ── Reinforcement on awareness ───────────────────────────────────────
        if awareness_emerged:
            for pat_id, amp, _cat in active:
                wave_mem.reinforce_pattern(pat_id, boost * synchrony)
            identity.wave_patterns = wave_mem.to_list()
            logger.debug(
                "GlobalCouplerLayer: awareness_emerged  r=%.3f  n=%d  user=%s  tick=%d",
                synchrony, n, identity.user_id, tick,
            )

        # ── Publish to cache (readable by later layers / _build_response) ────
        ctx.cache.extra["global_synchrony"] = synchrony
        ctx.cache.extra["awareness_emerged"] = awareness_emerged


def _top_patterns(
    wave_mem,
    top_n: int,
    tick: int,
) -> List[Tuple[str, float, str]]:
    """Return list of (pattern_id, decayed_amplitude, category) for top-N patterns."""
    scored = []
    for pat in wave_mem._patterns:
        amp = pat.decayed_amplitude(tick)
        if amp > 0.01:
            scored.append((pat.pattern_id, amp, pat.category))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_n]
