"""
SensoryLayer — multi-channel sensory integration.

Reads:  ctx.cache.extra["_raw_sensory_inputs"] (set by engine before pipeline)
Writes: ctx.user.emotional_intensity, ctx.user.urgency
        ctx.cache.extra["sensory"], ctx.cache.extra["sensory_biases"]
        ctx.cache.extra["sensory_novelty_bias"]

Also writes a MemoryTrace to ctx.identity.raw_memory for every processed
request, seeding the subconscious/conscious pipeline with a raw imprint.
Observed != believed.  Remembered != accepted.
"""

from __future__ import annotations

import logging
import uuid

from app.core.identity_context import IdentityContext
from app.core.memory_trace import MemoryTrace, MemoryState, content_hash
from .base import MindLayer

logger = logging.getLogger(__name__)


class SensoryLayer(MindLayer):
    name = "sensory"

    def on_step(self, ctx: IdentityContext) -> None:
        raw_sensory: list = list(ctx.cache.extra.get("_raw_sensory_inputs", []))
        request = ctx.cache.extra.get("_request")
        if request is None:
            ctx.cache.extra["sensory_biases"] = {}
            ctx.cache.extra["sensory_novelty_bias"] = 0.0
            return

        try:
            from app.core.sensory_channel import encode_channel, language_channel_from_request
            from app.core.sensory_integrator import integrate_sensory_input, delta_to_pipeline_biases

            raw_sensory.append(
                language_channel_from_request(
                    request.input_text, request.emotional_state, request.urgency
                )
            )
            channel_features = [encode_channel(s) for s in raw_sensory]
            sensory = integrate_sensory_input(
                channel_features=channel_features,
                current_channel_models=ctx.identity.channel_models,
                urgency=request.urgency,
            )
            biases = delta_to_pipeline_biases(sensory.sensory_delta, request.urgency)

            ctx.user.emotional_intensity = float(min(1.0, max(0.0,
                ctx.user.emotional_intensity + biases["urgency_boost"]
            )))
            ctx.user.urgency = float(min(1.0, max(0.0,
                ctx.user.urgency + biases["urgency_boost"] * 0.5
            )))
            ctx.cache.extra["sensory"] = sensory
            ctx.cache.extra["sensory_biases"] = biases
            ctx.cache.extra["sensory_novelty_bias"] = 1.0 - (biases.get("novelty_reduction", 0) + 0.5)

            if sensory.updated_channel_models:
                ctx.identity.channel_models = sensory.updated_channel_models

        except Exception as err:
            logger.warning("SensoryLayer error (non-fatal): %s", err)
            ctx.cache.extra["sensory_biases"] = {}
            ctx.cache.extra["sensory_novelty_bias"] = 0.0

        # ── Write MemoryTrace for this input ──────────────────────────────────
        # Every observed input becomes a raw memory trace, regardless of whether
        # sensory integration succeeded.  Observed != believed.
        if request is not None:
            try:
                raw_text = getattr(request, "input_text", "") or ""
                urgency  = float(getattr(request, "urgency", 0.3))
                emo      = getattr(request, "emotional_state", "neutral") or "neutral"
                # Map common emotional states to an emotional_charge value
                _CHARGE = {
                    "neutral": 0.0, "calm": 0.1, "curious": 0.2,
                    "happy": 0.3, "excited": 0.4,
                    "sad": -0.3, "anxious": -0.4, "fearful": -0.5,
                    "angry": -0.35, "distressed": -0.6,
                }
                charge = _CHARGE.get(emo.lower(), 0.0)

                trace = MemoryTrace(
                    trace_id=str(uuid.uuid4()),
                    source="user_input",
                    content_hash=content_hash(raw_text),
                    activation=min(1.0, 0.40 + urgency * 0.40),
                    moral_risk=0.0,         # MoralLayer / SubconsciousLayer tags this later
                    confidence=0.5,
                    emotional_charge=charge,
                    state=MemoryState.RAW_OBSERVED,
                    formed_tick=ctx.identity.total_requests,
                    last_tick=ctx.identity.total_requests,
                    leakage_rate=0.04,
                )
                raw_mem = ctx.identity.raw_memory
                raw_mem.traces.append(trace)
                raw_mem.total_traces_formed += 1
                raw_mem.last_tick = ctx.identity.total_requests

                # Rolling window — evict oldest non-permanent traces when over cap
                if len(raw_mem.traces) > raw_mem.max_traces:
                    _PERMANENT_STATES = {
                        MemoryState.STABLE_WISDOM, MemoryState.IDENTITY_ROOT,
                        MemoryState.QUARANTINED, MemoryState.REFLECTED_LEARNING,
                    }
                    evictable = [
                        i for i, t in enumerate(raw_mem.traces)
                        if t.state not in _PERMANENT_STATES
                    ]
                    if evictable:
                        del raw_mem.traces[evictable[0]]

                ctx.cache.extra["_new_trace_id"] = trace.trace_id
            except Exception as trace_err:
                logger.debug("SensoryLayer: trace write failed (non-fatal): %s", trace_err)
