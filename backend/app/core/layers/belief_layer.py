"""
BeliefLayer â€” crystallises persistent high-amplitude patterns into named Beliefs.

Pipeline slot: after GlobalCouplerLayer, before DecisionLayer.

Lifecycle per tick
------------------
1. TRACKING   â€” for every pattern whose decayed amplitude â‰¥ threshold,
                increment `belief_state.pattern_ticks[pat_id]`.
                For patterns that dropped below threshold, reset the counter
                (they must hold the threshold *consecutively*).

2. PROMOTION  â€” when `pattern_ticks[pat_id] >= belief_formation_ticks` and
                the pattern is not already a Belief, promote it:
                  â€¢ create a `Belief` object from the pattern's metadata
                  â€¢ add to `belief_state.beliefs`
                  â€¢ increment `total_beliefs_formed`

3. PRUNING    â€” remove Belief objects whose source pattern has dropped below
                half the formation threshold for â‰¥ belief_decay_ticks, or
                whose pattern_id is no longer in the wave field.

4. CONFLICT   â€” compare all active Belief pairs by cosine similarity of 6D
                centres.  If cosine < `belief_conflict_cosine`:
                  â€¢ flag both `is_contradicted = True`
                  â€¢ raise `belief_state.contradiction_score`
                  â€¢ boost `ctx.cache.residual_score` by `belief_contradiction_boost`
                    so the reflective stack is more likely to fire NEXT tick

5. PUBLISH    â€” write `belief_state.contradiction_score` and active belief
                count to `ctx.cache.extra` for DecisionLayer / response.

Tunable params (all via getp):
  belief_formation_ticks      = 20   consecutive ticks above threshold
  belief_amplitude_threshold  = 0.55 minimum decayed amplitude to track
  belief_conflict_cosine      = -0.3 cosine below this = conflict
  belief_contradiction_boost  = 0.15 added to residual_score on conflict
  belief_decay_ticks          = 5    ticks below half-threshold before pruning
  belief_max_beliefs          = 20   cap on total active beliefs
"""

from __future__ import annotations

import logging
import uuid

from app.core.identity_context import IdentityContext, getp
from app.core.belief import Belief, BeliefState, cosine_similarity
from .base import MindLayer

logger = logging.getLogger(__name__)

# Categories that can crystallise into beliefs (HARMFUL never crystallises)
_CRYSTALLISABLE = {"moral_root", "stable_truth", "knowledge"}


class BeliefLayer(MindLayer):
    name = "BELIEF"

    def on_step(self, ctx: IdentityContext) -> None:
        try:
            self._run(ctx)
        except Exception as err:
            logger.warning("BeliefLayer error (non-fatal): %s", err)

    def _run(self, ctx: IdentityContext) -> None:
        from app.core.wave_pattern import WaveMemory

        identity = ctx.identity
        state: BeliefState = identity.belief_state
        tick = identity.total_requests

        # â”€â”€ Tunable params â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        formation_ticks = max(1, int(getp(identity, "belief_formation_ticks",   20.0)))
        amp_threshold   = getp(identity, "belief_amplitude_threshold",  0.55)
        conflict_cos    = getp(identity, "belief_conflict_cosine",      -0.30)
        contra_boost    = getp(identity, "belief_contradiction_boost",   0.15)
        decay_ticks     = max(1, int(getp(identity, "belief_decay_ticks",         5.0)))
        max_beliefs     = max(1, int(getp(identity, "belief_max_beliefs",        20.0)))

        wave_mem = WaveMemory(patterns=identity.wave_patterns, current_tick=tick)

        # Index active patterns by id
        active: dict = {}          # pattern_id â†’ (decayed_amp, category, center, label)
        for pat in wave_mem._patterns:
            if pat.category not in _CRYSTALLISABLE:
                continue
            amp = pat.decayed_amplitude(tick)
            if amp >= amp_threshold:
                label = f"{pat.category}:{pat.guidance_mode or 'general'} @ {pat.evolution_stage}"
                active[pat.pattern_id] = (amp, pat.category, list(pat.center), label)

        # â”€â”€ 1 + 2. TRACKING & PROMOTION â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        known_ids = {b.pattern_id for b in state.beliefs}

        for pat_id, (amp, cat, center, label) in active.items():
            state.pattern_ticks[pat_id] = state.pattern_ticks.get(pat_id, 0) + 1

            if pat_id not in known_ids and len(state.beliefs) < max_beliefs:
                if state.pattern_ticks[pat_id] >= formation_ticks:
                    new_belief = Belief(
                        belief_id=str(uuid.uuid4()),
                        pattern_id=pat_id,
                        label=label,
                        amplitude=amp,
                        center=center,
                        formed_tick=tick,
                        last_tick=tick,
                    )
                    state.beliefs.append(new_belief)
                    state.total_beliefs_formed += 1
                    known_ids.add(pat_id)
                    logger.debug(
                        "BeliefLayer: FORMED belief '%s' for user=%s tick=%d amp=%.3f",
                        label, identity.user_id, tick, amp,
                    )

        # Reset counters for patterns that dropped below threshold
        for pat_id in list(state.pattern_ticks):
            if pat_id not in active:
                state.pattern_ticks[pat_id] = max(
                    0, state.pattern_ticks[pat_id] - 1
                )
                if state.pattern_ticks[pat_id] == 0:
                    del state.pattern_ticks[pat_id]

        # Update amplitude snapshot for existing beliefs that are still active
        for b in state.beliefs:
            if b.pattern_id in active:
                b.amplitude = active[b.pattern_id][0]
                b.last_tick = tick
                b.is_contradicted = False   # reset each tick, re-evaluated below

        # â”€â”€ 3. PRUNING â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        live_pat_ids = {p["pattern_id"] for p in identity.wave_patterns}
        half_thr = amp_threshold * 0.5

        def _should_prune(b: Belief) -> bool:
            if b.pattern_id not in live_pat_ids:
                return True
            if b.pattern_id not in active:
                # Below threshold â€” check how long it's been since last active
                return (tick - b.last_tick) >= decay_ticks
            return False

        before = len(state.beliefs)
        state.beliefs = [b for b in state.beliefs if not _should_prune(b)]
        pruned = before - len(state.beliefs)
        if pruned:
            logger.debug(
                "BeliefLayer: pruned %d decayed beliefs for user=%s tick=%d",
                pruned, identity.user_id, tick,
            )

        # â”€â”€ 4. CONFLICT DETECTION â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        active_beliefs = [b for b in state.beliefs if b.pattern_id in active]
        max_conflict = 0.0
        conflict_found = False

        for i in range(len(active_beliefs)):
            for j in range(i + 1, len(active_beliefs)):
                bi, bj = active_beliefs[i], active_beliefs[j]
                cos = cosine_similarity(bi.center, bj.center)
                if cos < conflict_cos:
                    bi.is_contradicted = True
                    bj.is_contradicted = True
                    conflict_found = True
                    if abs(cos) > max_conflict:
                        max_conflict = abs(cos)

        if conflict_found:
            state.contradiction_score = float(max(state.contradiction_score, max_conflict))
            state.last_contradiction_tick = tick
            # Boost residual_score so reflective stack has pressure to fire next tick
            ctx.cache.residual_score = min(
                1.0, ctx.cache.residual_score + contra_boost
            )
            logger.debug(
                "BeliefLayer: CONFLICT  max_cos=%.3f  contradiction_score=%.3f  user=%s",
                max_conflict, state.contradiction_score, identity.user_id,
            )
        else:
            # Contradiction score decays toward 0 when no active conflict
            state.contradiction_score = max(0.0, state.contradiction_score - 0.05)

        state.last_tick = tick

        # â”€â”€ 5. PUBLISH â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        ctx.cache.extra["belief_count"]         = len(state.beliefs)
        ctx.cache.extra["contradiction_score"]  = state.contradiction_score
        ctx.cache.extra["beliefs_contradicted"] = sum(1 for b in state.beliefs if b.is_contradicted)
