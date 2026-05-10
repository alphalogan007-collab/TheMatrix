"""routes_wisdom_sync.py — Receive wisdom bundles from cloud minds.

A cloud mind finishes processing a video, then POSTs the resulting
wisdom entries here.  This endpoint pushes each entry into seed:input
so the LOCAL seed_mind processes it through the full pentagon topology.

This is the correct flow:
  Cloud slave processes video → POST /admin/wisdom/sync
  → local seed:input ← slave wisdom pushed as new seed events
  → local seed_mind reads seed:input → searches guidance:corpus
  → pushes enriched packet into space:layer1
  → 19 local workers oscillate through all 5 domains
  → new wisdom written to guidance:corpus by local topology

The slave's discovery becomes a seed thought in the local mind.
The local topology decides what to do with it — not the slave.

Routes:
  POST /admin/wisdom/sync   — receive wisdom bundle from a cloud mind
  GET  /admin/wisdom/sync   — list recent sync receipts
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

REDIS_URL     = os.environ.get("REDIS_URL", "redis://redis:6379/0")
SEED_STREAM   = "seed:input"         # local topology reads from here
EVENTS_STREAM = "spirit:events"      # local /world viewer watches this
DONE_KEY      = "yt:queue:done"
CLAIMED_KEY   = "yt:queue:claimed"

# In-memory receipt log (last 100)
_receipts: list[dict[str, Any]] = []


class WisdomEntry(BaseModel):
    file_id: str
    title: str
    content: str
    source: str = ""
    chars: int = 0


class WisdomSyncBody(BaseModel):
    mind_id: str                        # which cloud mind sent this
    source_url: str                     # the YouTube video URL that was processed
    source_title: str = ""
    wisdom_entries: list[WisdomEntry]   # wisdom produced


@router.post("/admin/wisdom/sync")
async def wisdom_sync(body: WisdomSyncBody):
    """Receive wisdom from a cloud mind and write to guidance:corpus."""
    if not body.wisdom_entries:
        raise HTTPException(status_code=400, detail="no wisdom_entries provided")

    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    pushed = 0
    try:
        ts = datetime.now(timezone.utc).isoformat()

        # Push each wisdom entry into seed:input so the LOCAL topology processes it.
        # The local seed_mind reads this stream, searches guidance:corpus for context,
        # then oscillates it through all 19 layers. The slave's discovery becomes
        # a new thought in the local mind — not written directly to corpus.
        for entry in body.wisdom_entries:
            content = (
                f"[Cloud Mind: {body.mind_id}]\n"
                f"Source: {body.source_title or entry.title}\n"
                f"URL: {body.source_url}\n\n"
                f"{entry.content}"
            )
            await r.xadd(
                SEED_STREAM,
                {
                    "input_type": "text",
                    "content":    content[:50_000],
                    "source":     entry.source or f"cloud:{body.mind_id}:{body.source_url}",
                    "session_id": uuid.uuid4().hex,
                    "ts":         ts,
                    # Tag so local topology knows this came from a slave
                    "origin":     "cloud_mind",
                    "mind_id":    body.mind_id,
                },
                maxlen=50_000,
                approximate=True,
            )
            pushed += 1

        # Notify /world viewer
        await r.xadd(
            EVENTS_STREAM,
            {
                "type":         "slave_synced",
                "mind_id":      body.mind_id,
                "source_url":   body.source_url,
                "source_title": body.source_title or "?",
                "seed_entries": str(pushed),
                "ts":           ts,
            },
            maxlen=50_000,
            approximate=True,
        )

        # Mark done in queue tracking
        done_record = json.dumps({
            "url":      body.source_url,
            "title":    body.source_title,
            "mind_id":  body.mind_id,
            "pushed":   pushed,
            "done_at":  ts,
        })
        await r.lpush(DONE_KEY, done_record)
        await r.hdel(CLAIMED_KEY, body.source_url)

        # Local receipt log
        receipt = {
            "mind_id":      body.mind_id,
            "source_url":   body.source_url,
            "source_title": body.source_title,
            "seed_entries": pushed,
            "ts":           ts,
        }
        _receipts.insert(0, receipt)
        if len(_receipts) > 100:
            _receipts.pop()

        return {"seed_pushed": pushed, "mind_id": body.mind_id}

    finally:
        await r.aclose()


@router.get("/admin/wisdom/sync")
async def wisdom_sync_list():
    """Return recent wisdom sync receipts."""
    return {"receipts": _receipts[:50]}
