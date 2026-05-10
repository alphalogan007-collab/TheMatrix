"""
convergence_event_bus.py — In-memory pub/sub for convergence events.

Architecture
------------
When a convergence event fires inside the pipeline (ConvergenceCognitionLayer
sets ctx.cache.extra["convergence_event"] = True), the engine publishes a
structured payload to this bus keyed by user_id.

Any number of SSE subscribers can be waiting on that user_id.  Each subscriber
holds its own asyncio.Queue.  The bus fan-outs to all active queues for that
user, then drops the message (fire-and-forget).  If a subscriber's queue is
full it is silently skipped — slow consumers do not block the pipeline.

This module is process-local.  It does NOT persist across server restarts and
does NOT work in multi-process deployments.  For multi-process setups, replace
`publish` with a Redis PUBLISH call and add a listener task in startup.

Usage
-----
    # In engine (on convergence event):
    await convergence_event_bus.publish(user_id, payload_dict)

    # In SSE route (per connected client):
    q = convergence_event_bus.subscribe(user_id)
    try:
        event = await asyncio.wait_for(q.get(), timeout=30.0)
        yield f"data: {json.dumps(event)}\n\n"
    finally:
        convergence_event_bus.unsubscribe(user_id, q)
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Dict, List

logger = logging.getLogger(__name__)

# user_id → list of subscriber queues
_subscribers: Dict[str, List[asyncio.Queue]] = defaultdict(list)

# Maximum payload queue depth per subscriber
_QUEUE_MAX = 50


def subscribe(user_id: str) -> asyncio.Queue:
    """Register a new subscriber for *user_id*.  Returns its queue."""
    q: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAX)
    _subscribers[user_id].append(q)
    logger.debug("convergence_event_bus: subscriber added for user=%s total=%d",
                 user_id, len(_subscribers[user_id]))
    return q


def unsubscribe(user_id: str, q: asyncio.Queue) -> None:
    """Remove *q* from the subscriber list for *user_id*."""
    subs = _subscribers.get(user_id)
    if subs and q in subs:
        subs.remove(q)
        logger.debug("convergence_event_bus: subscriber removed for user=%s remaining=%d",
                     user_id, len(subs))


def subscriber_count(user_id: str) -> int:
    """Return the number of active subscribers for *user_id*."""
    return len(_subscribers.get(user_id, []))


async def publish(user_id: str, event: dict) -> None:
    """Fan-out *event* to all active subscribers for *user_id*.

    Non-blocking: full queues are skipped (slow consumer protection).
    """
    subs = list(_subscribers.get(user_id, []))
    if not subs:
        return
    for q in subs:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            logger.debug("convergence_event_bus: queue full for user=%s, event dropped", user_id)
    logger.debug("convergence_event_bus: published to %d subscriber(s) for user=%s",
                 len(subs), user_id)
