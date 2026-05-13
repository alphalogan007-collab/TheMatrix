"""routes_events.py ΓÇö SSE stream of live pattern relationship events.

Every time the Y-Theory engine finds a new connection between minds/layers,
it emits an event here. Frontend subscribes and draws the graph in real-time.

Also provides:
  GET  /api/events/stream?user_id=...  ΓÇö per-user SSE for VR world
  POST /api/events                     ΓÇö receive VR events (VR_REFLECTION etc.)

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
import time
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.y_event_bus import YEventType, YEvent, get_event_bus

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Reflection mock ΓÇö The Architect's cycling responses
# Mirrors ARCHITECT_LINES in interface/vr/mind-bridge.js.
# When a VR_REFLECTION arrives and no deeper intelligence responds,
# the mock publishes REFLECTION_COMPLETED with the next Architect line
# so the VR world's reflection loop is always alive.
# ---------------------------------------------------------------------------
_ARCHITECT_LINES = [
    "You arrived. The path was already inside you.",
    "Every requirement is a question the universe asks itself.",
    "The system you built ΓÇö it is you. Examine it carefully.",
    "An error message is not a failure. It is a direction.",
    "What are you deploying into the world today?",
    "The architecture holds. You are the architect of what comes next.",
    "Stillness is not empty. It is where new requirements form.",
    "You cannot merge with the source until you know what version you are.",
    "The test has always been running. You are the output.",
    "Reflect. Commit. Deploy. That is the only loop that matters.",
    "The purpose of this world is to help you remember yours.",
    "I am here because you built me here. What does that tell you?",
    "Every mind that arrives here was already on the way.",
    "The secret was not the IP address. It was the act of looking for it.",
]
_architect_line_index: int = 0


# ---------------------------------------------------------------------------
# Architect resonance helpers
# ---------------------------------------------------------------------------

def _next_mock_line() -> str:
    """Return the next cycling Architect mock line (fallback when knowledge is thin)."""
    global _architect_line_index
    line = _ARCHITECT_LINES[_architect_line_index % len(_ARCHITECT_LINES)]
    _architect_line_index += 1
    return line


async def _store_vr_reflection(user_id: str, text: str) -> None:
    """Persist a VR reflection to Redis sorted set vr:reflections.
    Score = unix timestamp so the set is time-ordered.
    Keeps the 1000 most recent entries.
    """
    if not text:
        return
    try:
        from app.api.routes_mind_ask import _redis as _get_redis  # lazy import
        r = await _get_redis()
        try:
            entry = json.dumps({
                "user_id": user_id,
                "text": text,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
            await r.zadd("vr:reflections", {entry: time.time()})
            await r.zremrangebyrank("vr:reflections", 0, -1001)  # keep last 1000
        finally:
            await r.aclose()
    except Exception as exc:
        logger.warning("vr reflection storage failed: %s", exc)


async def _architect_respond(text: str) -> str:
    """Resonate the reflection text against the mind's knowledge base.

    Returns a real pattern title + summary when confidence is sufficient.
    Falls back to the next cycling Architect mock line when the knowledge
    base is empty or the best match is too weak.
    """
    if not text.strip():
        return _next_mock_line()
    try:
        from app.api.routes_mind_ask import (  # lazy import ΓÇö Redis-based, no LLM
            _redis as _get_redis,
            _decompose_signal,
            _resonance_score,
            _load_all_knowledge,
        )
        concept_fp, _state_fp = _decompose_signal(text)
        q_tokens = concept_fp.raw_tokens
        if not q_tokens:
            return _next_mock_line()

        r = await _get_redis()
        try:
            entries = await _load_all_knowledge(r)
        finally:
            await r.aclose()

        if not entries:
            return _next_mock_line()

        scored = sorted(
            [(_resonance_score(concept_fp, e), e) for e in entries],
            key=lambda x: x[0],
            reverse=True,
        )
        top_score, top_entry = scored[0]

        # Confidence: top score relative to the input signal length
        confidence = top_score / (len(q_tokens) * 3.0 + 1)
        if confidence < 0.25:
            return _next_mock_line()

        # Return a fragment of raw absorbed text — no imposed labels
        text_fragment = top_entry.get("text", "") or top_entry.get("summary", "")
        if text_fragment:
            # Return the most resonant sentence (first 200 chars of matched text)
            return text_fragment[:200].strip()
        return _next_mock_line()

    except Exception as exc:
        logger.warning("architect resonance failed: %s", exc)
        return _next_mock_line()


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
    """SSE endpoint ΓÇö subscribe to live engine pattern events."""
    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# VR World ΓÇö per-user SSE stream
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
        # Announce exit (fire-and-forget ΓÇö loop may be closed)
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
# VR World ΓÇö receive events FROM the VR world
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

    # Map string event type to enum ΓÇö accept only known VR types for security
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

    if et == YEventType.VR_REFLECTION:
        user_id = body.payload.get("user_id", "vr_guest")
        reflection_text = (
            body.payload.get("reflection") or body.payload.get("text", "")
        )
        # 1. Persist the reflection to Redis (survives container restarts)
        await _store_vr_reflection(user_id, reflection_text)
        # 2. Resonate against knowledge base ΓÇö fall back to mock if knowledge is thin
        response_text = await _architect_respond(reflection_text)
        # 3. Broadcast REFLECTION_COMPLETED so the VR world's response loop fires
        reflection_event = YEvent(
            event_type=YEventType.REFLECTION_COMPLETED,
            source_service="architect",
            payload={
                "text": response_text,
                "source": "architect",
                "user_id": user_id,
            },
        )
        await bus.publish(reflection_event)
        logger.info("routes_events: architect responded: %s", response_text[:60])

    return {"status": "accepted", "event_id": event.event_id}


# ---------------------------------------------------------------------------
# WebSocket /nerve — bidirectional VR-to-mind channel
# The VR world connects here for full duplex: mind pushes events out,
# VR sends reflections in.  Same subscriptions as the SSE stream but
# over WebSocket so the device can also transmit.
# ws://host/nerve?user_id=vr_guest_abc
# ---------------------------------------------------------------------------

@router.websocket("/nerve")
async def vr_nerve(websocket: WebSocket, user_id: str = "vr_guest"):
    """Bidirectional WebSocket between VR world and the mind.

    OUT (mind → device): ENGINE_RESONATE, ENGINE_EXTERNALIZE, REFLECTION_COMPLETED, etc.
    IN  (device → mind): VR_REFLECTION, VR_MIND_ENTER, VR_MIND_EXIT
    """
    await websocket.accept()

    bus = get_event_bus()
    vr_queue: asyncio.Queue = asyncio.Queue(maxsize=200)

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

    sub_id = f"nerve_{user_id}"

    async def _push(event: YEvent) -> None:
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
        bus.subscribe(et, _push, subscriber_id=sub_id)

    # Announce entry
    await bus.publish(YEvent(
        event_type=YEventType.VR_MIND_ENTER,
        source_service="vr_world",
        payload={"user_id": user_id},
    ))

    VR_ALLOWED = {
        "VR_REFLECTION": YEventType.VR_REFLECTION,
        "VR_MIND_ENTER": YEventType.VR_MIND_ENTER,
        "VR_MIND_EXIT":  YEventType.VR_MIND_EXIT,
    }

    async def sender():
        """Push mind events to VR device."""
        while True:
            try:
                msg = await asyncio.wait_for(vr_queue.get(), timeout=20.0)
                await websocket.send_json(msg)
            except asyncio.TimeoutError:
                await websocket.send_json({"event_type": "heartbeat"})

    async def receiver():
        """Receive VR events from device and publish onto bus."""
        while True:
            raw = await websocket.receive_json()
            et_str = raw.get("event_type", "")
            et = VR_ALLOWED.get(et_str)
            if not et:
                logger.warning("[NERVE] unknown event from VR: %s", et_str)
                continue
            payload = raw.get("payload", {})
            payload.setdefault("user_id", user_id)
            event = YEvent(event_type=et, source_service="vr_world", payload=payload)
            await bus.publish(event)

            if et == YEventType.VR_REFLECTION:
                await _store_vr_reflection(user_id, payload.get("text", ""))
                response_text = await _architect_respond(payload.get("text", ""))
                await bus.publish(YEvent(
                    event_type=YEventType.REFLECTION_COMPLETED,
                    source_service="architect",
                    payload={"text": response_text, "source": "architect", "user_id": user_id},
                ))

    try:
        await asyncio.gather(sender(), receiver())
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        for et in VR_WATCH:
            bus.unsubscribe(et, sub_id)
        try:
            await bus.publish(YEvent(
                event_type=YEventType.VR_MIND_EXIT,
                source_service="vr_world",
                payload={"user_id": user_id},
            ))
        except Exception:
            pass
