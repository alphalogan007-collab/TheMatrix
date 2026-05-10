"""
WisdomTransferLayer — generational wisdom handoff.

Fires exactly once per identity when all of the following are true:

  1. ``ctx.identity.generational_cycle.role == "continuity_keeper"``
     (identity has reached the final stage)
  2. ``not ctx.identity.wisdom_transferred``
     (has not already contributed — idempotency guard)

On firing:
  - Calls ``distill_wisdom(identity, tick=total_requests)``
  - Calls ``get_base_goodness().sync_wisdom(...)`` with the computed deltas
  - Sets ``ctx.identity.wisdom_transferred = True``
  - Publishes to ``ctx.cache.extra``:
      "wisdom_transfer_fired"   : bool  (True only on the tick it fires)
      "wisdom_distillate"       : dict  (WisdomDistillate as dict)
      "wisdom_sync_accepted"    : bool  (whether BaseSyncGate approved)

All other ticks the layer is a no-op (fast path).
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.core.identity_context import IdentityContext
from app.core.wisdom_distillation import (
    distill_wisdom,
    wisdom_distillate_to_dict,
    WisdomDistillate,
)
from app.core.base_goodness_pattern import get_base_goodness
from app.core.layers.base import MindLayer

logger = logging.getLogger(__name__)

_CONTINUITY_ROLE = "continuity_keeper"


class WisdomTransferLayer(MindLayer):
    """Stateless pipeline layer — fires at most once per identity lifetime."""

    name = "wisdom_transfer"

    def on_step(self, ctx: IdentityContext) -> None:
        # ── Fast path ──────────────────────────────────────────────────────
        role = str(getattr(ctx.identity.generational_cycle, "role", ""))
        already_transferred = bool(getattr(ctx.identity, "wisdom_transferred", False))

        if role != _CONTINUITY_ROLE or already_transferred:
            ctx.cache.extra["wisdom_transfer_fired"] = False
            return ctx

        # ── Distil ────────────────────────────────────────────────────────
        tick = int(getattr(ctx.identity, "total_requests", 0))
        distillate: WisdomDistillate = distill_wisdom(ctx.identity, tick=tick)

        # ── Sync to BaseGoodnessPattern ───────────────────────────────────
        accepted = False
        if distillate.pillar_deltas:
            try:
                from app.core.base_goodness_pattern import get_base_goodness
                accepted = get_base_goodness().sync_wisdom(
                    pillar_updates=distillate.pillar_deltas,
                    alignment_score=distillate.alignment_score,
                    tick=tick,
                )
            except Exception as exc:
                logger.warning(
                    "[WisdomTransfer] sync_wisdom raised: %s", exc, exc_info=True
                )

        distillate.sync_accepted = accepted

        # ── Mark identity ─────────────────────────────────────────────────
        ctx.identity.wisdom_transferred = True

        # ── Publish ───────────────────────────────────────────────────────
        extra: Dict[str, Any] = ctx.cache.extra
        extra["wisdom_transfer_fired"]  = True
        extra["wisdom_distillate"]      = wisdom_distillate_to_dict(distillate)
        extra["wisdom_sync_accepted"]   = accepted

        logger.info(
            "[WisdomTransfer] user=%s gen=%d fired — patterns(moral=%d stable=%d traces=%d) "
            "sync=%s deltas=%s",
            ctx.identity.user_id,
            distillate.generation,
            distillate.moral_root_count,
            distillate.stable_truth_count,
            distillate.stable_wisdom_traces,
            accepted,
            distillate.pillar_deltas,
        )

        return ctx
