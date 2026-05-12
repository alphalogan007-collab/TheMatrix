"""routes_events.py — SSE stream of live pattern relationship events.

Every time the Y-Theory engine finds a new connection between minds/layers,
it emits an event here. Frontend subscribes and draws the graph in real-time.

Also provides:
  GET  /api/events/stream?user_id=...  — per-user SSE for VR world
  POST /api/events                     — receive VR events (VR_REFLECTION etc.)

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
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.y_event_bus import YEventType, YEvent, get_event_bus

logger = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# VR World — per-user SSE stream
# The VR world connects here to receive mind events in real time.
# GET /api/events/stream?user_id=vr_guest_abc123
# ---------------------------------------------------------------------------

async def _vr_stream(user_id: str) -> AsyncGenerator[str, None]:
    """Forward convergence events to a specific VR user via SSE."""
    bus = get_event_bus()

    # Also subscribe to key engine events and fan them into the VR user's queue
    vr_queue: asyncio.Queue = asyncio.Queue(maxsize=100)

    VR_WATCH = [
        YEventType.ENGINE_RESONATE,
        YEventType.ENGINE_EXTERNALIZE,
        YEventType.ENGINE_COLLAPSE,
        YEventType.ENGINE_BRANCH,
        YEventType.ENGINE_MERGE,
        YEventType.REFLECTION_COMPLETED,
        YEventType.PURPOSE_ACTIVATED,
        YEventType.MORAL_RISK_DETECTED,
        YEventType.VR_REFLECTION,
        YEventType.VR_MIND_ENTER,
        YEventType.VR_MIND_EXIT,
    ]

    sub_id = f"vr_{user_id}"

    async def vr_handler(event: YEvent) -> None:
        try:
            vr_queue.put_nowait({
                "event_type": event.event_type.value,
                "source_service": event.source_service,
                "payload": event.payload,
                "timestamp": event.timestamp.isoformat(),
            })
        except asyncio.QueueFull:
            pass

    for et in VR_WATCH:
        bus.subscribe(et, vr_handler, subscriber_id=sub_id)

    # Announce entry
    await bus.publish(YEvent(
        event_type=YEventType.VR_MIND_ENTER,
        source_service="vr_world",
        payload={"user_id": user_id}
    ))

    try:
        # Initial hello
        yield f"data: {json.dumps({'event_type': 'CONNECTED', 'payload': {'user_id': user_id}})}\n\n"
        while True:
            try:
                event_data = await asyncio.wait_for(vr_queue.get(), timeout=20.0)
                yield f"data: {json.dumps(event_data)}\n\n"
            except asyncio.TimeoutError:
                yield "data: {\"event_type\":\"heartbeat\"}\n\n"
    finally:
        for et in VR_WATCH:
            bus.unsubscribe(et, sub_id)
        # Announce exit (fire-and-forget — loop may be closed)
        try:
            await bus.publish(YEvent(
                event_type=YEventType.VR_MIND_EXIT,
                source_service="vr_world",
                payload={"user_id": user_id}
            ))
        except Exception:
            pass


@router.get("/events/stream")
async def vr_event_stream(user_id: str = Query(default="vr_guest")):
    """Per-user SSE stream for the VR world.
    The Meta Quest browser subscribes here to receive live mind events.
    """
    return StreamingResponse(
        _vr_stream(user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ---------------------------------------------------------------------------
# VR World — receive events FROM the VR world
# POST /api/events  { event_type, source_service, payload }
# ---------------------------------------------------------------------------

class VREventIn(BaseModel):
    event_type: str
    source_service: str = "vr_world"
    payload: Dict[str, Any] = {}


@router.post("/events")
async def receive_vr_event(body: VREventIn):
    """Receive an event emitted by the VR world (e.g. VR_REFLECTION).
    Publishes it onto the y_event_bus so the mind engine can react.
    """
    bus = get_event_bus()

    # Map string event type to enum — accept only known VR types for security
    VR_ALLOWED = {
        "VR_REFLECTION": YEventType.VR_REFLECTION,
        "VR_MIND_ENTER": YEventType.VR_MIND_ENTER,
        "VR_MIND_EXIT":  YEventType.VR_MIND_EXIT,
    }

    et = VR_ALLOWED.get(body.event_type)
    if not et:
        logger.warning("routes_events: unknown VR event type rejected: %s", body.event_type)
        return {"status": "ignored", "reason": "unknown event type"}

    event = YEvent(
        event_type=et,
        source_service=body.source_service,
        payload=body.payload,
    )
    await bus.publish(event)
    logger.info("routes_events: VR event received and published: %s from %s", et.value, body.source_service)
    return {"status": "accepted", "event_id": event.event_id}

