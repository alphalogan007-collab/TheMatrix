"""
y_event_bus.py — Universal event bus for the Y-Architecture.

This is the nervous system of the service-oriented identity architecture.
Every service communicates through this bus. Events are typed, observable,
and fan-out to all registered handlers.

The existing convergence_event_bus.py is kept for SSE streaming (user-facing).
This bus is internal — service-to-service, fully observable.

Event types follow the Y-Architecture processing flow:
  PATTERN_RECEIVED       — a new pattern/input entered a service
  MEMORY_ACTIVATED       — a memory was recalled
  ATTENTION_SELECTED     — attention focused on a specific element
  MORAL_RISK_DETECTED    — moral gate flagged a concern
  REFLECTION_COMPLETED   — a reflection cycle finished
  SERVICE_CALLED         — one service called another
  PURPOSE_ACTIVATED      — a purpose mind was engaged
  IDENTITY_UPDATED       — an identity's state changed
  CAPABILITY_USED        — a capability was invoked
  MEMORY_WRITTEN         — new memory was committed to any scope
  QUARANTINE_TRIGGERED   — content moved to quarantine scope
  CONSOLIDATION_STARTED  — sleep/consolidation cycle began
  CONSOLIDATION_DONE     — sleep/consolidation cycle completed

Architecture notes:
  - Process-local in-memory bus (same as convergence_event_bus)
  - For multi-process: replace _dispatch() with Redis PUBLISH
  - Rolling event history for observability (last 500 events)
  - Handlers subscribe by event type; errors are caught and logged
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

class YEventType(str, Enum):
    """All event types in the Y-Architecture event bus."""
    PATTERN_RECEIVED      = "PATTERN_RECEIVED"
    MEMORY_ACTIVATED      = "MEMORY_ACTIVATED"
    ATTENTION_SELECTED    = "ATTENTION_SELECTED"
    MORAL_RISK_DETECTED   = "MORAL_RISK_DETECTED"
    REFLECTION_COMPLETED  = "REFLECTION_COMPLETED"
    SERVICE_CALLED        = "SERVICE_CALLED"
    PURPOSE_ACTIVATED     = "PURPOSE_ACTIVATED"
    IDENTITY_UPDATED      = "IDENTITY_UPDATED"
    CAPABILITY_USED       = "CAPABILITY_USED"
    MEMORY_WRITTEN        = "MEMORY_WRITTEN"
    QUARANTINE_TRIGGERED  = "QUARANTINE_TRIGGERED"
    CONSOLIDATION_STARTED = "CONSOLIDATION_STARTED"
    CONSOLIDATION_DONE    = "CONSOLIDATION_DONE"
    OSCILLATION_REQUESTED = "OSCILLATION_REQUESTED"
    MIND_GRAPH_UPDATED    = "MIND_GRAPH_UPDATED"

    # -----------------------------------------------------------------------
    # Engine decision events — emitted by the Y-Engine after every cycle.
    # These are the DECISIONS of the engine, not observations.
    # The graph/body/scaling layers react to these; they never call back into
    # the engine. This is the clean separation: Engine decides, graph records,
    # body executes, scaling externalizes.
    #
    # Payload schema (all engine events):
    #   mind        : str   — which identity ran the cycle
    #   intent      : str   — classified intent of the incoming pattern
    #   depth       : int   — how many resonance loop passes were needed
    #   coherence   : float — 0.0–1.0, how well the pattern fit (1.0 = perfect)
    #   residual    : float — 0.0–1.0, unabsorbed difference (1.0 = total novelty)
    #   entry_count : int   — number of memory entries in the resonance pool
    # -----------------------------------------------------------------------

    # Identity can locally adapt — pattern absorbed within current structure.
    # residual small, loop stabilized quickly.
    ENGINE_DEFORM         = "ENGINE_DEFORM"

    # Incoming pattern strongly matches an existing entry — joined, not stored.
    ENGINE_MERGE          = "ENGINE_MERGE"

    # New motif attached to existing identity — gap was seeded as new entry.
    # payload extra: title of the new entry
    ENGINE_ATTACH         = "ENGINE_ATTACH"

    # One structure divided — stability detected across sub-domains (future).
    ENGINE_SPLIT          = "ENGINE_SPLIT"

    # Pattern incompatible with current identity — new branch synthesized.
    # `_self_expand()` was called. payload extra: synth_title
    ENGINE_BRANCH         = "ENGINE_BRANCH"

    # Leakage/lag/strain overwhelmed coherence — identity is at collapse risk.
    # Currently emitted when loop reaches max depth without stabilizing.
    ENGINE_COLLAPSE       = "ENGINE_COLLAPSE"

    # Loop stabilized — top resonant entries converged across passes.
    # This is the confirmation that the mind has a coherent answer.
    ENGINE_RESONATE       = "ENGINE_RESONATE"

    # A stable internal loop has become its own identity.
    # payload extra: candidate_mind_name (suggested name for new mind)
    ENGINE_EXTERNALIZE    = "ENGINE_EXTERNALIZE"

    # Purified wisdom returned upward — WISDOM_EXTRACTED written.
    # payload extra: wisdom_title
    ENGINE_RETURN_TO_BASE = "ENGINE_RETURN_TO_BASE"

    # Pattern has meaning but is unsafe/unstable — held in quarantine.
    ENGINE_QUARANTINE     = "ENGINE_QUARANTINE"

    # Pattern has no coherent persistence — discarded as noise.
    # residual too low AND coherence too low — pattern matches nothing.
    ENGINE_IGNORE_AS_NOISE = "ENGINE_IGNORE_AS_NOISE"


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------

@dataclass
class YEvent:
    """A typed event on the Y event bus."""
    event_type: YEventType
    source_service: str                   # which service emitted this
    payload: Dict[str, Any]              # event-specific data
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    event_id: str = field(
        default_factory=lambda: uuid.uuid4().hex[:12]
    )
    target_service: Optional[str] = None  # None = broadcast to all handlers

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "source_service": self.source_service,
            "target_service": self.target_service,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
        }


# Handler type: async callable receiving a YEvent
Handler = Callable[[YEvent], Awaitable[None]]


# ---------------------------------------------------------------------------
# Event bus
# ---------------------------------------------------------------------------

class YEventBus:
    """
    In-process pub/sub event bus for Y-Architecture services.

    Handlers subscribe by event type. When an event is published:
      1. All global handlers (*) for that event type are called
      2. If event.target_service is set, only that service's handlers fire
      3. Recent events are kept in a rolling log for inspection

    This is intentionally process-local. For multi-process deployments,
    replace the dispatch logic with a Redis PUBLISH call (same interface).
    """

    _HISTORY_MAX = 500

    def __init__(self) -> None:
        # event_type.value → list of (subscriber_id, handler)
        self._handlers: Dict[str, List[tuple[str, Handler]]] = defaultdict(list)
        self._history: List[YEvent] = []

    # ------------------------------------------------------------------
    # Subscribe / unsubscribe
    # ------------------------------------------------------------------

    def subscribe(
        self,
        event_type: YEventType,
        handler: Handler,
        subscriber_id: str = "*",
    ) -> None:
        """Register a handler for an event type.

        subscriber_id: identifies the subscriber.
          - Use '*' to receive all events of this type (broadcast).
          - Use a specific service_id to receive only events targeted at it.
        """
        self._handlers[event_type.value].append((subscriber_id, handler))
        logger.debug(
            "y_event_bus: %s subscribed to %s", subscriber_id, event_type.value
        )

    def unsubscribe(self, event_type: YEventType, subscriber_id: str) -> None:
        """Remove all handlers registered by subscriber_id for this event type."""
        key = event_type.value
        self._handlers[key] = [
            (sid, h) for sid, h in self._handlers[key] if sid != subscriber_id
        ]

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    async def publish(self, event: YEvent) -> None:
        """Fan-out event to all matching subscribers.

        Non-blocking: handler errors are caught and logged so a bad
        handler never blocks the pipeline.
        """
        # Record in rolling history
        self._history.append(event)
        if len(self._history) > self._HISTORY_MAX:
            self._history = self._history[-self._HISTORY_MAX :]

        handlers = self._handlers.get(event.event_type.value, [])
        if not handlers:
            return

        for subscriber_id, handler in handlers:
            # Broadcast handlers ('*') always fire.
            # Targeted handlers only fire when event.target_service matches.
            if subscriber_id == "*" or event.target_service in (None, subscriber_id):
                try:
                    await handler(event)
                except Exception as exc:
                    logger.warning(
                        "y_event_bus: handler error [%s/%s]: %s",
                        subscriber_id,
                        event.event_type.value,
                        exc,
                    )

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def recent(
        self,
        event_type: Optional[YEventType] = None,
        source: Optional[str] = None,
        limit: int = 50,
    ) -> List[YEvent]:
        """Return recent events, optionally filtered by type or source."""
        events = self._history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if source:
            events = [e for e in events if e.source_service == source]
        return events[-limit:]

    def summary(self) -> Dict[str, int]:
        """Return count of events by type in current history."""
        counts: Dict[str, int] = defaultdict(int)
        for e in self._history:
            counts[e.event_type.value] += 1
        return dict(counts)

    def history_size(self) -> int:
        return len(self._history)


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------

_bus: Optional[YEventBus] = None


def get_event_bus() -> YEventBus:
    """Return the process-wide YEventBus singleton."""
    global _bus
    if _bus is None:
        _bus = YEventBus()
    return _bus


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

async def emit(
    event_type: YEventType,
    source_service: str,
    payload: Dict[str, Any],
    target_service: Optional[str] = None,
) -> None:
    """Emit an event on the global bus. Import this for quick usage."""
    bus = get_event_bus()
    event = YEvent(
        event_type=event_type,
        source_service=source_service,
        payload=payload,
        target_service=target_service,
    )
    await bus.publish(event)


def emit_sync(
    event_type: YEventType,
    source_service: str,
    payload: Dict[str, Any],
) -> None:
    """Fire-and-forget emit for sync contexts (no await, no handlers called).
    Records in history only — use in sync code paths."""
    bus = get_event_bus()
    event = YEvent(
        event_type=event_type,
        source_service=source_service,
        payload=payload,
    )
    bus._history.append(event)
    if len(bus._history) > bus._HISTORY_MAX:
        bus._history = bus._history[-bus._HISTORY_MAX :]
