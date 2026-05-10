"""
MoralLayer — moral kernel evaluation connected to the live wave field.

Reads:  ctx.identity.moral_state, ctx.identity.wave_patterns,
        ctx.cache.manipulation_signals, ctx.cache.extra["_request"]
Writes: ctx.identity.moral_state, ctx.cache.moral_alignment,
        ctx.cache.is_blocked, ctx.cache.correction_note,
        ctx.cache.extra["moral_result"], ctx.cache.extra["moral_boost"],
        ctx.cache.extra["wave_moral_amp"]
"""

from __future__ import annotations

import logging

from app.core.identity_context import IdentityContext
from .base import MindLayer

logger = logging.getLogger(__name__)


class MoralLayer(MindLayer):
    name = "moral"

    def on_step(self, ctx: IdentityContext) -> None:
        from app.core.moral_kernel import run_moral_kernel
        from app.core.wave_pattern import WaveMemory

        request = ctx.cache.extra.get("_request")

        # Compute live moral field amplitude from MORAL_ROOT wave patterns
        try:
            wave_mem = WaveMemory(
                patterns=ctx.identity.wave_patterns,
                current_tick=ctx.identity.total_requests,
            )
            wave_moral_amp = wave_mem.moral_amplitude()
        except Exception:
            wave_moral_amp = 0.82  # safe fallback

        ctx.cache.extra["wave_moral_amp"] = wave_moral_amp

        moral_result, updated_moral_state, moral_boost = run_moral_kernel(
            proposed_content=request.input_text if request else "",
            harm_signals=ctx.cache.manipulation_signals,
            moral_state=ctx.identity.moral_state,
            wave_moral_amplitude=wave_moral_amp,
            current_tick=ctx.identity.total_requests,
        )

        ctx.identity.moral_state = updated_moral_state
        ctx.cache.moral_alignment = moral_result.alignment_score
        ctx.cache.is_blocked = moral_result.is_blocked
        ctx.cache.correction_note = getattr(moral_result, "correction_note", "")
        ctx.cache.extra["moral_result"] = moral_result
        ctx.cache.extra["moral_boost"] = moral_boost

        # ── Tag moral_risk on the most recent raw/subconscious trace ──────────
        from app.core.moral_kernel import MoralVerdict
        from app.core.memory_trace import MemoryState
        _RISK_MAP = {
            MoralVerdict.BLOCKED:              1.00,
            MoralVerdict.SIGNIFICANT_CONCERN:  0.70,
            MoralVerdict.MINOR_CONCERN:        0.30,
            MoralVerdict.ALIGNED:              0.00,
        }
        risk = _RISK_MAP.get(moral_result.verdict, 0.0)
        if risk > 0.0:
            _TAGGABLE = {MemoryState.RAW_OBSERVED, MemoryState.SUBCONSCIOUS_TRACE}
            for trace in reversed(ctx.identity.raw_memory.traces):
                if trace.state in _TAGGABLE:
                    trace.moral_risk = risk
                    if moral_result.is_blocked:
                        trace.is_quarantined = True
                        trace.state = MemoryState.QUARANTINED
                    break
