"""
GenerationalCycleLayer — pipeline layer that drives stage advancement.

Reads convergence / moral / reflection signals from context, calls
advance_generational_cycle(), and publishes the current leakage profile
so that wave_pulse_worker can scale decay rates.

Outputs written to ctx.cache.extra
-----------------------------------
current_stage       : str   — name of the current stage
current_stage_idx   : int   — numeric index
generation          : int   — generation number
leakage_profile     : dict  — {category: float multiplier}
stage_advanced      : bool  — True only on the tick advancement occurs
new_stage           : str   — name of the stage just entered (when advanced)
role                : str   — earned role (may be empty)
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.core.identity_context import IdentityContext
from app.core.generational_cycle import (
    GenerationalCycleState,
    advance_generational_cycle,
)
from app.core.layers.base import MindLayer

logger = logging.getLogger(__name__)


class GenerationalCycleLayer(MindLayer):
    """Stateless pipeline layer — all mutable state lives on ctx."""

    name = "generational_cycle"

    # ------------------------------------------------------------------
    def on_step(self, ctx: IdentityContext) -> None:
        gc: GenerationalCycleState = ctx.identity.generational_cycle

        # ── Pull signals from context ──────────────────────────────────
        cc = ctx.identity.convergence_cognition
        awakening_score    = float(getattr(cc, "awakening_score", 0.0))
        service_impulse    = float(getattr(cc, "service_impulse", 0.0))
        convergence_events = int(getattr(cc, "convergence_event_count", 0))

        moral_alignment   = float(getattr(ctx.cache, "moral_alignment", 0.5))
        total_requests    = int(getattr(ctx.identity, "total_requests", 0))
        total_reflections = int(getattr(ctx.identity, "total_reflections", 0))

        # ── Advance ───────────────────────────────────────────────────
        old_idx = gc.current_stage_idx
        new_gc = advance_generational_cycle(
            gc,
            total_requests=total_requests,
            total_reflections=total_reflections,
            awakening_score=awakening_score,
            convergence_events=convergence_events,
            moral_alignment=moral_alignment,
            service_impulse=service_impulse,
        )

        advanced = new_gc.current_stage_idx > old_idx

        # ── Write back to identity ────────────────────────────────────
        ctx.identity.generational_cycle = new_gc

        # ── Publish to cache.extra ────────────────────────────────────
        extra: Dict[str, Any] = ctx.cache.extra
        extra["current_stage"]     = new_gc.current_stage_name
        extra["current_stage_idx"] = new_gc.current_stage_idx
        extra["generation"]        = new_gc.generation
        extra["leakage_profile"]   = dict(new_gc.leakage_profile)
        extra["stage_advanced"]    = advanced
        extra["new_stage"]         = new_gc.current_stage_name if advanced else ""
        extra["role"]              = new_gc.role

        if advanced:
            logger.info(
                "[GenerationalCycle] user=%s advanced to stage=%s "
                "(gen=%d, tick=%d, role=%s)",
                getattr(ctx.identity, "user_id", "?"),
                new_gc.current_stage_name,
                new_gc.generation,
                total_requests,
                new_gc.role or "none",
            )
