"""
ConsciousLayer -- attention-selection gate between subconscious and conscious workspace.

Pipeline slot: after BeliefLayer, before DecisionLayer.

"Conscious = focused attention-field + selected thought stream"

Per-tick logic
--------------
1. ATTENTION SELECTION
   Score each ThoughtCandidate in identity.thought_queue using a weighted
   composite (attention_score) biased by:
   - ctx.cache.residual_score  (confusion boosts unresolved thoughts)
   - user urgency              (high urgency boosts high-activation thoughts)
   - moral_risk gate           (risky thoughts get attention penalty)
   Select top-K (K = getp("conscious_max_active", 3)).

2. MOVE to ConsciousWorkspace
   Merge selected thoughts into identity.conscious_workspace.active_thoughts.
   Evict thoughts that have been in workspace > conscious_evict_ticks without
   a reflection cycle firing.

3. TRACK reflection pressure
   If no reflection fired this tick (ctx.cache.extra["_reflection_fired"] not
   set), increment workspace.cycles_without_reflection.  When this exceeds
   conscious_reflection_pressure (10) the value is published so downstream
   layers can nudge reflection.

4. PUBLISH
   ctx.cache.extra["active_thoughts"]       -- list of serialised ThoughtCandidates
   ctx.cache.extra["conscious_focus_count"] -- how many thoughts are active
   ctx.cache.extra["conscious_overflow"]    -- True if queue > max_active
   ctx.cache.extra["reflection_pressure"]  -- cycles_without_reflection

Tunable params (via getp):
  conscious_max_active          = 3   thoughts selected per tick
  conscious_max_workspace       = 5   max thoughts kept in workspace
  conscious_evict_ticks         = 10  evict workspace thought after N ticks idle
  conscious_moral_gate          = 0.7 moral_risk above this -> attention penalty
  conscious_reflection_pressure = 10  log warning above this many idle cycles
"""
from __future__ import annotations

import logging

from app.core.identity_context import IdentityContext, getp
from app.core.memory_trace import MemoryState, ThoughtCandidate
from .base import MindLayer

logger = logging.getLogger(__name__)


class ConsciousLayer(MindLayer):
    name = "conscious"

    def on_step(self, ctx: IdentityContext) -> None:
        try:
            self._run(ctx)
        except Exception as err:
            logger.warning("ConsciousLayer error (non-fatal): %s", err)

    def _run(self, ctx: IdentityContext) -> None:
        identity  = ctx.identity
        tick      = identity.total_requests
        workspace = identity.conscious_workspace

        # -- Tunable params
        max_active   = max(1, int(getp(identity, "conscious_max_active",          3.0)))
        max_ws       = max(1, int(getp(identity, "conscious_max_workspace",       5.0)))
        evict_ticks  = max(1, int(getp(identity, "conscious_evict_ticks",        10.0)))
        moral_gate   = getp(identity, "conscious_moral_gate",           0.70)
        refl_pressure = max(1, int(getp(identity, "conscious_reflection_pressure", 10.0)))

        residual = ctx.cache.residual_score
        urgency  = ctx.user.urgency

        # -- 1. Score + select from thought queue
        def _score(t: ThoughtCandidate) -> float:
            base = t.attention_score()
            base += 0.10 * residual * t.unresolved_score
            base += 0.05 * urgency  * t.activation_strength
            if t.moral_risk > moral_gate:
                base *= 0.60
            return base

        queue_overflow = len(identity.thought_queue) > max_active
        selected = sorted(identity.thought_queue, key=_score, reverse=True)[:max_active]

        # -- 2. Advance linked memory trace states to CONSCIOUS_FOCUS
        for t in selected:
            for trace in identity.raw_memory.traces:
                if trace.trace_id in t.source_trace_ids:
                    if trace.state not in (
                        MemoryState.REFLECTED_LEARNING,
                        MemoryState.STABLE_WISDOM,
                        MemoryState.QUARANTINED,
                        MemoryState.IDENTITY_ROOT,
                    ):
                        trace.state = MemoryState.CONSCIOUS_FOCUS

        # -- 3. Evict stale workspace thoughts
        workspace.active_thoughts = [
            t for t in workspace.active_thoughts
            if (tick - t.formed_tick) < evict_ticks
        ]

        # -- 4. Merge selected into workspace (no duplicate thought_ids)
        existing_ids = {t.thought_id for t in workspace.active_thoughts}
        for t in selected:
            if t.thought_id not in existing_ids:
                workspace.active_thoughts.append(t)
                existing_ids.add(t.thought_id)

        # Cap workspace by score
        if len(workspace.active_thoughts) > max_ws:
            workspace.active_thoughts.sort(
                key=lambda t: t.attention_score(), reverse=True
            )
            workspace.active_thoughts = workspace.active_thoughts[:max_ws]

        workspace.last_tick = tick

        # -- 5. Track reflection pressure
        if ctx.cache.extra.get("_reflection_fired"):
            workspace.cycles_without_reflection = 0
        else:
            workspace.cycles_without_reflection += 1

        if workspace.cycles_without_reflection >= refl_pressure:
            logger.debug(
                "ConsciousLayer: reflection pressure high  user=%s cycles=%d",
                identity.user_id, workspace.cycles_without_reflection,
            )

        # -- 6. Publish
        ctx.cache.extra["active_thoughts"] = [
            {
                "thought_id":        t.thought_id,
                "activation":        round(t.activation_strength, 3),
                "relevance":         round(t.relevance, 3),
                "unresolved":        round(t.unresolved_score, 3),
                "moral_risk":        round(t.moral_risk, 3),
                "emotional_charge":  round(t.emotional_charge, 3),
                "suggested_question": t.suggested_question,
            }
            for t in workspace.active_thoughts
        ]
        ctx.cache.extra["conscious_focus_count"] = len(workspace.active_thoughts)
        ctx.cache.extra["conscious_overflow"]    = queue_overflow
        ctx.cache.extra["reflection_pressure"]   = workspace.cycles_without_reflection

        logger.debug(
            "ConsciousLayer: user=%s tick=%d queue=%d selected=%d workspace=%d",
            identity.user_id, tick, len(identity.thought_queue),
            len(selected), len(workspace.active_thoughts),
        )
