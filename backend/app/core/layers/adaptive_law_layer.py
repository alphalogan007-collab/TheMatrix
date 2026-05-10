"""
AdaptiveLawLayer — Step 14: λ/γ Auto-Tuning (Adaptive Law)

Pipeline slot: LAST in the pipeline (after DecisionLayer).

This layer measures the quality of the current tick and nudges tunable
params in ``ctx.identity.params`` by small δ each tick, keeping each param
within hard floors and ceilings.

Tuning philosophy
-----------------
* High closure + low contradiction  → mind is healthy; relax pressure
  sensitivity, lower belief formation threshold (trust comes easier).
* High boundary_flux (oscillation)  → mind is turbulent; raise pressure
  damping so it stabilises faster; filter subconscious queue more strictly.
* Persistent contradiction           → boost contradiction signal so
  BeliefLayer fires conflicts sooner and reflection cleans them up.
* High social alignment              → lower attract threshold (more
  receptive to aligned peers).
* Low closure / high residual        → strengthen reflection boost so
  reinforcement is more potent.

Immune params (never touched)
------------------------------
``moral_*``, ``reflect_boost`` when moral_alignment is below 0.5.

All changes are:
  1. ≤ _MAX_DELTA per tick          (incremental — no step-change shocks)
  2. Bounded by per-param floor/ceiling.
  3. Applied as: new = clamp(old + Δ, floor, ceiling)
  4. Only written when |Δ| > _MIN_DELTA  (no-op if signal is neutral).
"""
from __future__ import annotations

import logging
from typing import Dict, Tuple

from app.core.layers.base import MindLayer
from app.core.identity_context import IdentityContext, getp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-param tuning spec
# Format: param_key → (floor, ceiling, max_delta)
# ---------------------------------------------------------------------------
_PARAM_SPEC: Dict[str, Tuple[float, float, float]] = {
    # Oscillation
    "osc_pressure_tau":          (0.05, 0.70, 0.010),
    "osc_amp_tau":               (0.05, 0.50, 0.005),
    "osc_natural_frequency":     (0.02, 0.30, 0.002),
    "osc_entrainment_k":         (0.05, 0.60, 0.005),
    # Belief
    "belief_formation_ticks":    (5.0, 60.0, 0.50),
    "belief_amplitude_threshold":(0.35, 0.80, 0.005),
    "belief_contradiction_boost":(0.05, 0.40, 0.005),
    "belief_decay_ticks":        (2.0, 20.0, 0.20),
    "belief_max_beliefs":        (5.0, 40.0, 0.50),
    # Global coupler
    "coupler_k":                 (0.01, 0.20, 0.002),
    "coupler_awareness_threshold":(0.40, 0.90, 0.005),
    # Subconscious
    "subconscious_threshold":    (0.10, 0.70, 0.005),
    "subconscious_emotion_weight":(0.10, 0.80, 0.005),
    # Social field
    "social_pull_tau":           (0.02, 0.40, 0.005),
    "social_pressure_scale":     (0.05, 0.80, 0.005),
    "social_attract_threshold":  (0.05, 0.50, 0.005),
    "social_repel_threshold":    (-0.40, -0.02, 0.005),
    # Wave-observe
    "reflect_boost":             (0.01, 0.15, 0.002),
    "moral_boost":               (0.01, 0.15, 0.002),
}

# ---------------------------------------------------------------------------
# Default values matching each layer's own getp(..., default=X) calls.
# Used as fallback when a param has never been explicitly set.
# ---------------------------------------------------------------------------
_PARAM_DEFAULTS: Dict[str, float] = {
    "osc_pressure_tau":           0.30,
    "osc_amp_tau":                0.20,
    "osc_natural_frequency":      0.10,
    "osc_entrainment_k":          0.20,
    "belief_formation_ticks":    20.0,
    "belief_amplitude_threshold": 0.55,
    "belief_contradiction_boost": 0.15,
    "belief_decay_ticks":         5.0,
    "belief_max_beliefs":        20.0,
    "coupler_k":                  0.06,
    "coupler_awareness_threshold":0.70,
    "subconscious_threshold":     0.30,
    "subconscious_emotion_weight":0.40,
    "social_pull_tau":            0.10,
    "social_pressure_scale":      0.30,
    "social_attract_threshold":   0.15,
    "social_repel_threshold":    -0.10,
    "reflect_boost":              0.04,
    "moral_boost":                0.04,
}

# Never auto-tune these (moral immunity)
_IMMUNE_PREFIXES = ("moral_decay_rate", "moral_weight", "moral_alignment")

_MIN_DELTA = 1e-5   # ignore sub-threshold nudges
_PUBLISH_TOP_N = 5  # how many param changes to log


class AdaptiveLawLayer(MindLayer):
    name = "adaptive_law"

    def on_step(self, ctx: IdentityContext) -> None:
        try:
            self._run(ctx)
        except Exception as err:
            logger.warning("AdaptiveLawLayer error (non-fatal): %s", err)

    def _run(self, ctx: IdentityContext) -> None:
        identity = ctx.identity
        params   = identity.params  # mutable dict

        # ── Read signals ──────────────────────────────────────────────────
        closure      = float(ctx.cache.closure_score)         # 0–1 higher = resolved
        moral_align  = float(ctx.cache.moral_alignment)       # 0–1
        contradiction= float(identity.belief_state.contradiction_score)  # 0–1
        residual     = float(ctx.cache.residual_score)        # 0–1
        boundary_flux= float(ctx.cache.extra.get("boundary_flux", 0.0))  # 0–1
        inner_p      = float(ctx.cache.extra.get("inner_pressure", 0.3))
        synchrony    = float(ctx.cache.extra.get("global_synchrony", 0.0))
        social_aligned   = int(ctx.cache.extra.get("aligned_peer_count", 0))
        social_repelled  = int(ctx.cache.extra.get("repelled_peer_count", 0))
        social_pressure  = float(ctx.cache.extra.get("social_pressure", 0.0))

        # Composite health score 0–1 (high = healthy tick)
        health = (
            0.40 * closure
            + 0.30 * moral_align
            + 0.15 * synchrony
            + 0.15 * (1.0 - contradiction)
        )

        # ── Build Δ map ───────────────────────────────────────────────────
        deltas: Dict[str, float] = {}

        # --- Oscillation pressure tau
        # High flux → system unstable → faster damping (↑ tau)
        # Low flux + good health → system stable → slower damping (↓ tau)
        if boundary_flux > 0.55:
            deltas["osc_pressure_tau"] = +0.008
        elif boundary_flux < 0.25 and health > 0.65:
            deltas["osc_pressure_tau"] = -0.005

        # --- Oscillation amp tau
        # High inner pressure → dampen amplitude estimation (↑ tau)
        if inner_p > 0.70:
            deltas["osc_amp_tau"] = +0.003
        elif inner_p < 0.25 and health > 0.60:
            deltas["osc_amp_tau"] = -0.002

        # --- Coupler K (synchrony coupling strength)
        # High synchrony → coupler is working → can afford to reduce K
        # Low synchrony + healthy → push harder
        if synchrony > 0.80 and health > 0.70:
            deltas["coupler_k"] = -0.002
        elif synchrony < 0.30 and health > 0.50:
            deltas["coupler_k"] = +0.002

        # --- Coupler awareness threshold
        # If sync is consistently high lower the threshold slightly (easier to emerge)
        if synchrony > 0.75 and health > 0.65:
            deltas["coupler_awareness_threshold"] = -0.003
        elif synchrony < 0.40:
            deltas["coupler_awareness_threshold"] = +0.002

        # --- Belief formation threshold
        # High closure + low contradiction → trust easier (↓ threshold)
        # High contradiction → more evidence needed before believing (↑ threshold)
        if closure > 0.70 and contradiction < 0.20:
            deltas["belief_amplitude_threshold"] = -0.004
        elif contradiction > 0.55:
            deltas["belief_amplitude_threshold"] = +0.004

        # --- Belief contradiction boost
        # Persistent high contradiction → amplify signal so it fires reflection sooner
        if contradiction > 0.50:
            deltas["belief_contradiction_boost"] = +0.004
        elif contradiction < 0.15 and health > 0.65:
            deltas["belief_contradiction_boost"] = -0.003

        # --- Belief formation ticks
        # High residual → slow down belief formation (need more confirming ticks)
        if residual > 0.60:
            deltas["belief_formation_ticks"] = +0.30
        elif residual < 0.20 and health > 0.65:
            deltas["belief_formation_ticks"] = -0.20

        # --- Subconscious threshold
        # Turbulent (high flux) → raise threshold (quieter queue)
        # Stable + healthy → lower threshold (more thoughts surface)
        if boundary_flux > 0.60:
            deltas["subconscious_threshold"] = +0.004
        elif boundary_flux < 0.20 and health > 0.60:
            deltas["subconscious_threshold"] = -0.003

        # --- Subconscious emotion weight
        # High moral alignment → emotional signals matter more
        if moral_align > 0.75:
            deltas["subconscious_emotion_weight"] = +0.003
        elif moral_align < 0.35:
            deltas["subconscious_emotion_weight"] = -0.002

        # --- Social attract threshold
        # More aligned peers reliably → lower attract threshold (be more open)
        if social_aligned >= 2 and social_pressure > 0.20:
            deltas["social_attract_threshold"] = -0.004
        elif social_repelled > social_aligned and social_repelled >= 2:
            deltas["social_attract_threshold"] = +0.004

        # --- Social pull tau
        # High social pressure → respond faster to peers
        if social_pressure > 0.40:
            deltas["social_pull_tau"] = +0.004
        elif social_pressure < 0.05 and health > 0.55:
            deltas["social_pull_tau"] = -0.003

        # --- Reflect boost
        # Low closure → more reinforcement needed
        # Immune when moral_alignment is low (can't self-reinforce if morally adrift)
        if moral_align >= 0.50:
            if closure < 0.30:
                deltas["reflect_boost"] = +0.002
            elif closure > 0.75 and health > 0.70:
                deltas["reflect_boost"] = -0.001

        # --- Moral boost: immune — never auto-tuned (only hand-crafted or none)

        # ── Apply Δ with clamping ─────────────────────────────────────────
        applied: Dict[str, Tuple[float, float, float]] = {}  # key → (old, delta, new)
        for key, delta in deltas.items():
            if key.startswith(_IMMUNE_PREFIXES):
                continue
            spec = _PARAM_SPEC.get(key)
            if spec is None:
                continue
            floor, ceiling, max_d = spec
            # Clamp delta to spec max
            delta = max(-max_d, min(max_d, delta))
            if abs(delta) < _MIN_DELTA:
                continue
            old_val = getp(identity, key, _PARAM_DEFAULTS.get(key, (floor + ceiling) / 2.0))
            new_val = max(floor, min(ceiling, old_val + delta))
            if abs(new_val - old_val) < _MIN_DELTA:
                continue
            params[key] = round(new_val, 6)
            applied[key] = (old_val, delta, new_val)

        # ── Publish summary ───────────────────────────────────────────────
        ctx.cache.extra["adaptive_health"]       = round(health, 4)
        ctx.cache.extra["adaptive_params_changed"] = len(applied)

        if applied:
            # Log top N (by |delta|)
            top = sorted(applied.items(), key=lambda kv: abs(kv[1][1]), reverse=True)
            for k, (old, d, nv) in top[:_PUBLISH_TOP_N]:
                logger.debug(
                    "AdaptiveLaw: user=%s  %s  %.5f → %.5f  (Δ%+.5f)",
                    identity.user_id, k, old, nv, d,
                )
            ctx.cache.extra["adaptive_top_change"] = top[0][0] if top else ""
        else:
            ctx.cache.extra["adaptive_top_change"] = ""

        logger.debug(
            "AdaptiveLawLayer: user=%s health=%.3f changed=%d",
            identity.user_id, health, len(applied),
        )

        # ── Write tick-summary (episodic) trace ───────────────────────────────
        # One trace per tick capturing what happened: moral verdict, closure,
        # dominant belief. This is the episodic record the subconscious can
        # reference on future ticks.  Source = "tick_summary".
        try:
            from app.core.memory_trace import MemoryTrace, MemoryState, content_hash
            import uuid as _uuid

            moral_result = ctx.cache.extra.get("moral_result")
            verdict_str  = moral_result.verdict.value if moral_result else "clear"
            dom_belief   = ctx.cache.extra.get("dominant_peer_id", "")  # best available proxy

            # Content key: stable hash of tick fingerprint so repeated similar
            # ticks accumulate the same content_hash (enables STABLE_WISDOM later)
            summary_key  = f"{verdict_str}|clos={round(closure, 1)}|contra={round(contradiction, 1)}"
            c_hash       = content_hash(summary_key)

            tick_trace = MemoryTrace(
                trace_id       = str(_uuid.uuid4()),
                source         = "tick_summary",
                content_hash   = c_hash,
                activation     = round(health, 3),
                moral_risk     = 0.0 if verdict_str == "clear" else (
                    1.0 if verdict_str == "blocked" else
                    0.70 if "significant" in verdict_str else 0.30
                ),
                confidence     = round(closure, 3),
                emotional_charge = round(float(ctx.user.urgency) * 0.5, 3),
                state          = MemoryState.RAW_OBSERVED,
                formed_tick    = identity.total_requests,
                last_tick      = identity.total_requests,
                leakage_rate   = 0.02,   # summaries decay slowly
            )
            identity.raw_memory.traces.append(tick_trace)
            identity.raw_memory.total_traces_formed += 1
            identity.raw_memory.last_tick = identity.total_requests
        except Exception as _te:
            logger.debug("AdaptiveLawLayer: tick_summary trace failed (non-fatal): %s", _te)
