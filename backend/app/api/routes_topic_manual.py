"""routes_topic_manual.py — Feed topics to the mind via body->mind oscillation.

All topics enter via seed:input -> body(13) -> space(8) -> digital(5) -> ether(3) -> aether(2) -> unity(1)
No LLM. Knowledge comes from the guidance corpus (pre-loaded files in guidance/inbox/).

Endpoints:
  POST /manual/start           - queue a single topic into seed:input
  POST /manual/queue           - queue multiple topics at once
  DELETE /manual/queue/{topic} - remove a pending topic from queue
  POST /manual/stop            - clear queue
  GET  /manual/status          - queue + status
"""

from __future__ import annotations

import logging
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter()
logger = logging.getLogger("topic_manual")

_queue: list[str] = []
_state: dict = {
    "running": False, "topic": None, "chapter": None, "chapter_num": 0,
    "total_chapters": 0, "entries_written": 0, "errors": 0, "last_error": None,
    "started_at": None, "done_at": None, "stop_requested": False,
}
_completed: list[dict] = []


class ManualRequest(BaseModel):
    topic: str

class QueueRequest(BaseModel):
    topics: list[str]


@router.post("/manual/start")
async def start_manual(req: ManualRequest):
    """Queue a topic via seed:input so it flows body->space->digital->ether->aether->unity."""
    topic = req.topic.strip()
    if not topic:
        return {"error": "topic cannot be empty"}
    settings = get_settings()
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        msg_id = await r.xadd("seed:input", {
            "content": topic, "input_type": "text",
            "source": "manual", "session_id": uuid.uuid4().hex,
        }, maxlen=5000, approximate=True)
    finally:
        await r.aclose()
    _queue.append(topic)
    logger.info("Manual topic queued: %s -> seed:input %s", topic, msg_id)
    return {"status": "queued", "topic": topic, "stream": "seed:input", "msg_id": msg_id}


@router.post("/manual/queue")
async def add_to_queue(req: QueueRequest):
    """Push multiple topics into the mind via seed:input (body->mind flow)."""
    settings = get_settings()
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    added = []
    try:
        for raw in req.topics:
            topic = raw.strip()
            if not topic:
                continue
            await r.xadd("seed:input", {
                "content": topic, "input_type": "text",
                "source": "manual_queue", "session_id": uuid.uuid4().hex,
            }, maxlen=5000, approximate=True)
            _queue.append(topic)
            added.append(topic)
    finally:
        await r.aclose()
    return {"added": added, "stream": "seed:input"}


@router.delete("/manual/queue/{topic}")
async def remove_from_queue(topic: str):
    if topic in _queue:
        _queue.remove(topic)
        return {"status": "removed", "topic": topic, "queue": list(_queue)}
    return {"status": "not_found", "topic": topic}


@router.post("/manual/stop")
async def stop_manual_queue():
    cleared = list(_queue)
    _queue.clear()
    _state["stop_requested"] = True
    return {"status": "queue_cleared", "cleared_topics": cleared,
            "note": "Topics already in seed:input will still be processed by the topology."}


@router.get("/manual/status")
async def manual_status():
    return {
        "running": _state["running"], "topic": _state["topic"],
        "entries_written": _state["entries_written"], "errors": _state["errors"],
        "queue": list(_queue), "completed": list(reversed(_completed)),
        "info": "Topics processed by topology workers (body->mind). No LLM.",
    }
