"""
ReflectionLayer — body-mind-meta prediction + losses.

Reads:  ctx.identity.reflective_stack, ctx.user, ctx.cache.residual_score
Writes: ctx.identity.reflective_stack, ctx.identity.total_reflections,
        ctx.cache.extra["rs_outputs"]
"""

from __future__ import annotations

from app.core.identity_context import IdentityContext
from app.core.reflective_stack import reflective_step
from app.core.memory_trace import MemoryState
from .base import MindLayer


class ReflectionLayer(MindLayer):
    name = "reflection"

    def on_step(self, ctx: IdentityContext) -> None:
        new_rs_state, rs_outputs = reflective_step(
            state=ctx.identity.reflective_stack,
            emotional_intensity=ctx.user.emotional_intensity,
            urgency=ctx.user.urgency,
            contradiction=ctx.cache.residual_score,
            novelty=0.40,
        )
        ctx.identity.reflective_stack = new_rs_state
        ctx.identity.total_reflections += int(rs_outputs.reflection_triggered)
        ctx.cache.extra["rs_outputs"] = rs_outputs

        # ── Advance conscious traces to REFLECTED_LEARNING when reflection fires ─
        if rs_outputs.reflection_triggered:
            tick = ctx.identity.total_requests
            for trace in ctx.identity.raw_memory.traces:
                if trace.state == MemoryState.CONSCIOUS_FOCUS:
                    trace.state    = MemoryState.REFLECTED_LEARNING
                    trace.last_tick = tick
            ctx.cache.extra["_reflection_fired"] = True
