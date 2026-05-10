"""
WorldInputLayer — injects reality-gated external signals into wave memory.

Position in pipeline: immediately after WaveObserveLayer (slot 8), before
SubconsciousLayer.  This placement means:
  - The moral kernel has already run (MoralLayer) — moral amplitude is live.
  - The wave field has already been observed this tick (WaveObserveLayer).
  - External signals enter AFTER internal state is updated, not before.
    The mind first processes itself, then considers the world.

Reads:
  ctx.identity.quarantine_memory  — QuarantineMemory sub-identity
  ctx.identity.wave_patterns       — current WavePattern list
  ctx.identity.total_requests      — current engine tick
  ctx.identity.evolution_stage     — used for context encoding
  ctx.identity.basin_state         — used for context encoding
  ctx.cache.extra["wave_mem"]      — WaveMemory already built by WaveObserveLayer
                                     (reused if present to avoid double-init)

Writes:
  ctx.identity.quarantine_memory   — updated signal statuses (APPROVED/REJECTED)
  ctx.identity.wave_patterns        — new KNOWLEDGE patterns from approved signals
  ctx.cache.extra["world_signals_approved"]  — int: count approved this tick
  ctx.cache.extra["world_signals_rejected"]  — int: count rejected this tick
  ctx.cache.extra["world_signals_injected"]  — int: count wave patterns spawned

Invariants:
  • Never touches MORAL_ROOT patterns — those have a separate reinforcement path.
  • If quarantine_memory is absent (old identity snapshots), this layer is a no-op.
  • Exceptions inside this layer are caught and logged — never propagate.
"""

from __future__ import annotations

import logging

from app.core.identity_context import IdentityContext
from app.core.wave_pattern import WaveMemory, encode_context
from app.core.world_adapter import WorldSignalStatus, process_quarantine
from .base import MindLayer

logger = logging.getLogger(__name__)

# Context vector parameters for world-sourced signals.
# External signals arrive at a "neutral stable" context — moderate closure,
# low urgency.  The mind is calm when it considers the outside world.
_WORLD_CLOSURE:       float = 0.60
_WORLD_URGENCY:       float = 0.20
_WORLD_GUIDANCE_MODE: str   = "world_input"
_WORLD_BASIN:         str   = "STABLE"
_WORLD_EMOTIONAL:     str   = "neutral"

# Max signals to inject per tick (prevents one tick being dominated by world input)
_BATCH_SIZE: int = 3


class WorldInputLayer(MindLayer):
    """Process quarantined world signals and inject approved ones into wave memory."""

    name = "world_input"

    def on_step(self, ctx: IdentityContext) -> None:
        qm = getattr(ctx.identity, "quarantine_memory", None)
        if qm is None:
            return

        # Fast-path: nothing pending
        pending = [s for s in qm.signals if s.status == WorldSignalStatus.QUARANTINED]
        if not pending:
            ctx.cache.extra.setdefault("world_signals_approved", 0)
            ctx.cache.extra.setdefault("world_signals_rejected", 0)
            ctx.cache.extra.setdefault("world_signals_injected", 0)
            return

        # Run reality check on up to _BATCH_SIZE pending signals
        try:
            approved = process_quarantine(
                qm,
                current_tick=ctx.identity.total_requests,
                batch_size=_BATCH_SIZE,
            )
        except Exception as exc:
            logger.warning("WorldInputLayer: quarantine processing error: %s", exc)
            return

        rejected_this_tick = len(pending[:_BATCH_SIZE]) - len(approved)
        ctx.cache.extra["world_signals_approved"] = len(approved)
        ctx.cache.extra["world_signals_rejected"] = rejected_this_tick

        if not approved:
            ctx.cache.extra.setdefault("world_signals_injected", 0)
            return

        # Reuse WaveMemory built by WaveObserveLayer if available; else build fresh
        wave_mem: WaveMemory = ctx.cache.extra.get("wave_mem")  # type: ignore[assignment]
        if wave_mem is None:
            wave_mem = WaveMemory(
                patterns=ctx.identity.wave_patterns,
                current_tick=ctx.identity.total_requests,
            )

        evolution_stage = ctx.identity.evolution_stage.name
        basin_state = (
            ctx.identity.basin_state.value
            if hasattr(ctx.identity.basin_state, "value")
            else str(ctx.identity.basin_state)
        )

        injected = 0
        for signal in approved:
            try:
                x = encode_context(
                    basin_state=_WORLD_BASIN,
                    guidance_mode=_WORLD_GUIDANCE_MODE,
                    emotional_state=_WORLD_EMOTIONAL,
                    evolution_stage=evolution_stage,
                    closure_score=_WORLD_CLOSURE,
                    urgency=_WORLD_URGENCY,
                )
                pattern_id, is_new = wave_mem.observe(
                    x=x,
                    closure=_WORLD_CLOSURE,
                    urgency=_WORLD_URGENCY,
                    guidance_mode=_WORLD_GUIDANCE_MODE,
                    evolution_stage=evolution_stage,
                    basin_state=_WORLD_BASIN,
                )
                injected += 1
                logger.debug(
                    "WorldInputLayer: signal=%s → pattern=%s new=%s tick=%d",
                    signal.signal_id, pattern_id, is_new, ctx.identity.total_requests,
                )
            except Exception as exc:
                logger.warning(
                    "WorldInputLayer: failed to inject signal %s: %s",
                    signal.signal_id, exc,
                )

        ctx.cache.extra["world_signals_injected"] = injected

        # Persist updated wave patterns (wave_mem was mutated in place)
        ctx.identity.wave_patterns = wave_mem.to_list()
        ctx.cache.extra["wave_mem"] = wave_mem
