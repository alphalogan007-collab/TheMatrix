"""
ConvergenceCognitionLayer — the awakening layer.

Reads:
    ctx.identity.reflective_stack   (reflection_triggered, total_reflections)
    ctx.cache.moral_alignment
    ctx.identity.belief_state.contradiction_score
    ctx.identity.total_requests
    ctx.identity.convergence_cognition   (current state)

Writes:
    ctx.identity.convergence_cognition   (updated state)
    ctx.cache.extra["convergence_event"] — True if a new event fired this tick
    ctx.cache.extra["active_question"]   — the question being held right now

Architecture rules:
    - No state lives in this layer.  State lives in ctx.identity.
    - One tick of work per call.  No loops, no heavy computation.
    - Reads BaseGoodnessPattern singleton but never mutates it.
      (Wisdom syncs happen via a separate process — see base_goodness_pattern.sync_wisdom())
"""

from __future__ import annotations

from app.core.identity_context import IdentityContext
from app.core.convergence_cognition import (
    advance_convergence_cognition,
    CONVERGENCE_DWELL_TICKS,
    CONVERGENCE_EVENT_THRESHOLD,
    _AWAKENING_HISTORY_MAX_LEN,
)
from app.core.dignity_charter import CONVERGENCE_QUESTIONS
from .base import MindLayer


class ConvergenceCognitionLayer(MindLayer):
    name = "convergence_cognition"

    def on_step(self, ctx: IdentityContext) -> None:
        # ── Gather input signals ─────────────────────────────────────────────
        rs = ctx.identity.reflective_stack
        reflection_triggered: bool = bool(rs.reflection_triggered)
        total_reflections: int = ctx.identity.total_reflections
        total_requests: int = ctx.identity.total_requests
        moral_alignment: float = float(ctx.cache.moral_alignment)
        contradiction_score: float = float(
            getattr(ctx.identity.belief_state, "contradiction_score", 0.0)
        )

        # ── Compute base_goodness_alignment from singleton ───────────────────
        from app.core.base_goodness_pattern import get_base_goodness
        bgp = get_base_goodness()
        cc = ctx.identity.convergence_cognition
        base_goodness_alignment = bgp.compute_alignment(
            moral_alignment=moral_alignment,
            awakening_score=cc.awakening_score,
            service_impulse=cc.service_impulse,
            reality_loop_recognition=cc.reality_loop_recognition,
        )

        # ── Advance state ─────────────────────────────────────────────────────
        new_cc = advance_convergence_cognition(
            ctx.identity.convergence_cognition,
            reflection_triggered=reflection_triggered,
            moral_alignment=moral_alignment,
            contradiction_score=contradiction_score,
            total_reflections=total_reflections,
            total_requests=total_requests,
            base_goodness_alignment=base_goodness_alignment,
        )
        ctx.identity.convergence_cognition = new_cc

        # ── Append to rolling awakening history ───────────────────────────────
        new_cc.awakening_history.append(round(new_cc.awakening_score, 5))
        if len(new_cc.awakening_history) > _AWAKENING_HISTORY_MAX_LEN:
            new_cc.awakening_history = new_cc.awakening_history[-_AWAKENING_HISTORY_MAX_LEN:]

        # ── Publish to cache ──────────────────────────────────────────────────
        # Did a new convergence event fire this tick?
        convergence_event_fired = (
            new_cc.convergence_event_count
            > ctx.identity.convergence_cognition.convergence_event_count  # already updated
        )
        # Simpler check: last_convergence_tick == current tick
        convergence_event_fired = (new_cc.last_convergence_tick == total_requests)

        if convergence_event_fired:
            ctx.cache.extra["convergence_event"] = True
            bgp.record_convergence_event()
        else:
            ctx.cache.extra.pop("convergence_event", None)

        # The active question being held by this identity this tick
        idx = new_cc.active_question_idx
        ctx.cache.extra["active_question"] = CONVERGENCE_QUESTIONS[
            min(idx, len(CONVERGENCE_QUESTIONS) - 1)
        ]
