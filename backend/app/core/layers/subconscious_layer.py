"""
SubconsciousLayer — the background memory-field that generates thought candidates.

Pipeline slot: after WaveObserveLayer, before GlobalCouplerLayer.

"Subconscious = background memory-field + latent pattern activation"

The subconscious is not silent storage.  It is a living background field:
  - memory traces in SUBCONSCIOUS_TRACE state interact with wave patterns
  - patterns oscillating above the latent threshold (0.30) are active even
    when no belief has crystallised around them
  - thought candidates surface from the intersection of trace activation and
    pattern amplitude — the mind keeps "thinking" even without input

Per-tick logic
--------------
1. PROMOTE RAW_OBSERVED → SUBCONSCIOUS_TRACE
   Every trace that just entered the field (RAW_OBSERVED) is promoted so
   it begins background interaction.

2. PRUNE expired traces
   Traces whose decayed_activation falls below the decay threshold are
   removed (except STABLE_WISDOM, IDENTITY_ROOT, QUARANTINED which are kept
   indefinitely).

3. BUILD latent pattern map
   Scan all wave patterns above subconscious_threshold (0.30 by default).
   These are the "background oscillations" — active but below conscious
   attention.

4. GENERATE ThoughtCandidates
   (a) Latent patterns without a crystallised belief → curiosity/pattern thoughts
   (b) Memory traces with high emotional_charge or long unresolved duration
       → emotional / recurrence thoughts
   (c) Contradicted beliefs → conflict-resolution thought candidates

5. MERGE + CAP
   Sort all candidates by attention_score(), keep top subconscious_max_queue.
   Older identical-source candidates are superseded by fresh ones.

6. PUBLISH
   ctx.cache.extra["thought_queue_size"]
   ctx.cache.extra["subconscious_traces"]
   ctx.cache.extra["latent_pattern_count"]

Tunable params (via getp):
  subconscious_threshold       = 0.30  min pattern amp to be "latent active"
  subconscious_max_queue       = 20    max ThoughtCandidates in queue
  subconscious_decay_threshold = 0.05  prune below this decayed activation
  subconscious_emotion_weight  = 0.40  weight of emotional_charge in scoring
"""

from __future__ import annotations

import logging
import uuid
from typing import List

from app.core.identity_context import IdentityContext, getp
from app.core.memory_trace import MemoryState, MemoryTrace, ThoughtCandidate
from .base import MindLayer

logger = logging.getLogger(__name__)


class SubconsciousLayer(MindLayer):
    name = "subconscious"

    def on_step(self, ctx: IdentityContext) -> None:
        try:
            self._run(ctx)
        except Exception as err:
            logger.warning("SubconsciousLayer error (non-fatal): %s", err)

    def _run(self, ctx: IdentityContext) -> None:
        from app.core.wave_pattern import WaveMemory

        identity = ctx.identity
        tick = identity.total_requests

        # ── Tunable params ────────────────────────────────────────────────────
        sub_thr    = getp(identity, "subconscious_threshold",       0.30)
        max_queue  = max(1, int(getp(identity, "subconscious_max_queue",        20.0)))
        decay_thr  = getp(identity, "subconscious_decay_threshold", 0.05)
        emotion_w  = getp(identity, "subconscious_emotion_weight",  0.40)

        # ── Build latent pattern map ──────────────────────────────────────────
        wave_mem = WaveMemory(patterns=identity.wave_patterns, current_tick=tick)
        latent: dict = {}   # pat_id → (amp, category, guidance_mode)
        for pat in wave_mem._patterns:
            amp = pat.decayed_amplitude(tick)
            if amp >= sub_thr:
                latent[pat.pattern_id] = (amp, pat.category, pat.guidance_mode or "general")

        # ── 1. Promote RAW_OBSERVED → SUBCONSCIOUS_TRACE ─────────────────────
        raw_mem = identity.raw_memory
        for trace in raw_mem.traces:
            if trace.state == MemoryState.RAW_OBSERVED:
                trace.state = MemoryState.SUBCONSCIOUS_TRACE
                trace.last_tick = tick

        # ── 2. Prune expired traces ───────────────────────────────────────────
        _PERMANENT = {
            MemoryState.STABLE_WISDOM,
            MemoryState.IDENTITY_ROOT,
            MemoryState.QUARANTINED,
            MemoryState.REFLECTED_LEARNING,
        }

        before = len(raw_mem.traces)
        raw_mem.traces = [
            t for t in raw_mem.traces
            if t.state in _PERMANENT or t.decayed_activation(tick) >= decay_thr
        ]
        pruned = before - len(raw_mem.traces)
        if pruned:
            logger.debug(
                "SubconsciousLayer: pruned %d traces  user=%s tick=%d",
                pruned, identity.user_id, tick,
            )

        # ── 3. Collect existing belief/contradicted ids ───────────────────────
        belief_pat_ids   = {b.pattern_id for b in identity.belief_state.beliefs}
        contradicted_ids = {
            b.pattern_id
            for b in identity.belief_state.beliefs if b.is_contradicted
        }

        # ── 4a. ThoughtCandidates from latent patterns ────────────────────────
        new_thoughts: List[ThoughtCandidate] = []

        for pat_id, (amp, cat, guidance) in latent.items():
            unresolved = 0.0
            if pat_id in contradicted_ids:
                unresolved = 0.75
            elif pat_id not in belief_pat_ids:
                unresolved = 0.15   # not yet a belief → mild curiosity pressure

            novelty  = min(1.0, amp / 0.80)
            moral_risk = 0.35 if cat == "harmful" else 0.05

            new_thoughts.append(ThoughtCandidate(
                thought_id=str(uuid.uuid4()),
                source_trace_ids=[],
                source_pattern_ids=[pat_id],
                activation_strength=amp,
                moral_risk=moral_risk,
                novelty=novelty,
                relevance=min(1.0, amp * 1.2),
                unresolved_score=unresolved,
                emotional_charge=0.0,
                formed_tick=tick,
            ))

        # ── 4b. ThoughtCandidates from memory traces ─────────────────────────
        for trace in raw_mem.traces:
            if trace.state not in (
                MemoryState.SUBCONSCIOUS_TRACE,
                MemoryState.ACTIVE_THOUGHT,
            ):
                continue

            live_act = trace.decayed_activation(tick)
            if live_act < decay_thr:
                continue

            emotional_abs = abs(trace.emotional_charge)
            ticks_active  = tick - trace.formed_tick
            recurrence    = min(1.0, ticks_active / 50.0)   # grows with age

            # Gate: only surface if salient enough
            gate = (
                0.40 * live_act
                + 0.30 * emotional_abs
                + 0.20 * trace.moral_risk
                + 0.10 * recurrence
            )
            if gate < 0.20:
                continue

            unresolved = (
                recurrence * 0.5
                + (0.5 if trace.moral_risk > 0.5 else 0.0)
            )

            new_thoughts.append(ThoughtCandidate(
                thought_id=str(uuid.uuid4()),
                source_trace_ids=[trace.trace_id],
                source_pattern_ids=list(trace.pattern_ids),
                activation_strength=live_act,
                moral_risk=trace.moral_risk,
                novelty=max(0.0, 1.0 - recurrence),
                relevance=(
                    emotion_w * emotional_abs
                    + (1.0 - emotion_w) * live_act
                ),
                unresolved_score=min(1.0, unresolved),
                emotional_charge=trace.emotional_charge,
                formed_tick=tick,
            ))

            # Advance trace state
            if trace.state == MemoryState.SUBCONSCIOUS_TRACE:
                trace.state = MemoryState.ACTIVE_THOUGHT

        # ── 5. Merge, sort, cap ───────────────────────────────────────────────
        # Prune expired entries in existing queue
        identity.thought_queue = [
            t for t in identity.thought_queue
            if t.decayed_activation(tick) >= decay_thr
        ]

        identity.thought_queue.extend(new_thoughts)
        identity.thought_queue.sort(
            key=lambda t: t.attention_score(), reverse=True
        )
        identity.thought_queue = identity.thought_queue[:max_queue]

        # ── 6. Publish ────────────────────────────────────────────────────────
        ctx.cache.extra["thought_queue_size"]    = len(identity.thought_queue)
        ctx.cache.extra["subconscious_traces"]   = len(raw_mem.traces)
        ctx.cache.extra["latent_pattern_count"]  = len(latent)

        logger.debug(
            "SubconsciousLayer: user=%s tick=%d latent=%d queue=%d traces=%d",
            identity.user_id, tick, len(latent),
            len(identity.thought_queue), len(raw_mem.traces),
        )
