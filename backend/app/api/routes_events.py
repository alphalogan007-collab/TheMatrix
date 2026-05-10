"""routes_events.py — SSE stream of live pattern relationship events.

Every time the Y-Theory engine finds a new connection between minds/layers,
it emits an event here. Frontend subscribes and draws the graph in real-time.

Event shape:
  {
    "type": "PATTERN_LINK",
    "from": "MoralLayer",
    "to": "BeliefLayer",
    "pattern": "moral_pressure_builds_belief",
    "strength": 0.82,
    "ts": "2026-05-05T..."
  }
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.y_event_bus import get_event_bus, YEventType

router = APIRouter()

_WATCH = [
    YEventType.PATTERN_RECEIVED,
    YEventType.MEMORY_WRITTEN,
    YEventType.IDENTITY_UPDATED,
    YEventType.MORAL_RISK_DETECTED,
    YEventType.REFLECTION_COMPLETED,
]


async def _event_stream() -> AsyncGenerator[str, None]:
    """Subscribe to the y_event_bus and forward events as SSE."""
    import uuid as _uuid
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    bus = get_event_bus()
    sub_id = f"sse_{_uuid.uuid4().hex[:8]}"

    async def handler(event: dict) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    for et in _WATCH:
        bus.subscribe(et, handler, subscriber_id=sub_id)

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
                payload = {
                    "type": event.get("event_type", "EVENT"),
                    "from": event.get("source_service", "engine"),
                    "to": event.get("target_service", "seed"),
                    "pattern": event.get("data", {}).get("pattern", ""),
                    "strength": event.get("data", {}).get("strength", 1.0),
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
                yield f"data: {json.dumps(payload)}\n\n"
            except asyncio.TimeoutError:
                yield "data: {\"type\":\"heartbeat\"}\n\n"
    finally:
        for et in _WATCH:
            bus.unsubscribe(et, sub_id)


@router.get("/events")
async def stream_events():
    """SSE endpoint — subscribe to live engine pattern events."""
    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
