"""routes_guidance.py — Guidance corpus read endpoints.

All Redis-only. No DB. Works in topology-only mode.

GET /guidance/list         — list all consumed files (metadata)
GET /guidance/{file_id}    — full content of one file
GET /guidance/events       — recent consumption events from Redis stream
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.redis_client import get_redis

router = APIRouter()


@router.get("/guidance/list")
async def list_guidance(
    limit: int = Query(100, le=500),
    redis=Depends(get_redis),
):
    """List all consumed guidance files (title, source, chars, ts). No content."""
    raw = await redis.hgetall("guidance:corpus")
    items = []
    for file_id, value in raw.items():
        try:
            entry = json.loads(value)
            items.append({
                "file_id": file_id,
                "title":   entry.get("title", ""),
                "source":  entry.get("source", ""),
                "chars":   entry.get("chars", 0),
                "ts":      entry.get("ts", ""),
            })
        except Exception:
            continue
    items.sort(key=lambda x: x["ts"], reverse=True)
    return items[:limit]


@router.get("/guidance/{file_id}")
async def get_guidance(
    file_id: str,
    redis=Depends(get_redis),
):
    """Get full content of a consumed guidance file."""
    raw = await redis.hget("guidance:corpus", file_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Guidance file not found")
    return json.loads(raw)


@router.get("/guidance/events/recent")
async def get_guidance_events(
    count: int = Query(20, le=100),
    redis=Depends(get_redis),
):
    """Recent guidance consumption events from Redis stream."""
    results = await redis.xrevrange("guidance:events", count=count)
    events = []
    for msg_id, fields in results:
        events.append({"msg_id": msg_id, **fields})
    return events
