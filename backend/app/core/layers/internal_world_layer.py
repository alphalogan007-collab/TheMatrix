"""
InternalWorldLayer — energy/stress dynamics from InternalWorld.

Reads:  ctx.identity.internal_world, ctx.user, ctx.cache.*
Writes: ctx.identity.internal_world, ctx.cache.extra["iw_outputs"]
"""

from __future__ import annotations

from app.core.identity_context import IdentityContext
from app.core.internal_world import InternalWorld, InternalWorldInputs
from .base import MindLayer

_internal_world = InternalWorld()


class InternalWorldLayer(MindLayer):
    name = "internal_world"

    def on_step(self, ctx: IdentityContext) -> None:
        biases = ctx.cache.extra.get("sensory_biases", {})

        iw_inputs = InternalWorldInputs(
            emotional_intensity=ctx.user.emotional_intensity,
            urgency=ctx.user.urgency,
            contradiction=ctx.cache.residual_score,
            manipulation_score=min(1.0, len(ctx.cache.manipulation_signals) * 0.25),
            novelty=0.40,
            nutrients=ctx.nutrients,
            toxicity=ctx.toxicity,
        )
        new_iw_state, iw_outputs = _internal_world.step(
            state=ctx.identity.internal_world,
            inputs=iw_inputs,
        )
        ctx.identity.internal_world = new_iw_state
        ctx.cache.extra["iw_outputs"] = iw_outputs
