"""routes_navigate.py — Navigator API.

The mind's field agent visits knowledge sources and reports back.
These endpoints let you direct the navigator: where to go, what's queued,
what has been visited, and what briefings were sent to the mind.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl

from app.db.redis_client import get_redis

router = APIRouter(prefix="/navigate", tags=["navigate"])

NAV_QUEUE    = "navigator:queue"
NAV_TARGETS  = "navigator:targets"
NAV_COOLDOWN = "navigator:cooldown"
NAV_LOG      = "navigator:log"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class VisitRequest(BaseModel):
    url: str
    label: Optional[str] = None
    intent: Optional[str] = None   # why the mind is visiting this — gives context to the briefing
    type: str = "html"             # "wikipedia" | "rss" | "html"
    revisit_hours: int = 24


class TargetConfig(BaseModel):
    label: str
    url: str
    type: str = "html"
    revisit_hours: int = 24
    priority: int = 5              # 1–10, higher = visited sooner
    intent: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/queue")
async def queue_visit(req: VisitRequest, r=Depends(get_redis)) -> dict:
    """Send the navigator to a specific URL immediately (jumps the queue).

    The navigator will visit this URL on its next cycle, extract understanding,
    and push a field briefing to seed:input for the mind to process.
    """
    label = req.label or req.url.split("/")[-1][:40]
    payload = {
        "url": req.url,
        "label": label,
        "intent": req.intent or "",
        "type": req.type,
        "revisit_hours": req.revisit_hours,
    }
    await r.lpush(NAV_QUEUE, json.dumps(payload))
    queue_len = await r.llen(NAV_QUEUE)
    return {
        "status": "queued",
        "label": label,
        "url": req.url,
        "queue_position": queue_len,
    }


@router.get("/status")
async def navigator_status(r=Depends(get_redis)) -> dict:
    """Current navigator state: queue depth, target count, recent activity."""
    queue_len   = await r.llen(NAV_QUEUE)
    target_count = await r.hlen(NAV_TARGETS)

    # Count URLs still on cooldown
    now = datetime.now(timezone.utc).timestamp()
    on_cooldown_count = await r.zcount(NAV_COOLDOWN, now, "+inf")

    # Last 3 visits from navigator:log
    recent_raw = await r.xrevrange(NAV_LOG, "+", "-", count=3)
    recent = []
    for _id, fields in recent_raw:
        recent.append({
            "ts":      fields.get("ts", ""),
            "label":   fields.get("label", ""),
            "host":    fields.get("host", ""),
            "title":   fields.get("title", ""),
            "success": fields.get("success") == "1",
        })

    return {
        "queue_pending": queue_len,
        "targets_configured": target_count,
        "targets_on_cooldown": on_cooldown_count,
        "targets_available": max(0, target_count - on_cooldown_count),
        "recent_visits": recent,
    }


@router.get("/log")
async def visit_log(limit: int = 20, r=Depends(get_redis)) -> dict:
    """Full visit history — what the navigator has visited and reported back on."""
    limit = min(limit, 100)
    raw = await r.xrevrange(NAV_LOG, "+", "-", count=limit)
    visits = []
    for _id, fields in raw:
        visits.append({
            "ts":        fields.get("ts", ""),
            "label":     fields.get("label", ""),
            "host":      fields.get("host", ""),
            "title":     fields.get("title", ""),
            "url":       fields.get("url", ""),
            "session_id": fields.get("session_id", ""),
            "success":   fields.get("success") == "1",
            "error":     fields.get("error", ""),
        })
    return {"count": len(visits), "visits": visits}


@router.get("/targets")
async def list_targets(r=Depends(get_redis)) -> dict:
    """All configured knowledge sources the navigator visits regularly."""
    raw = await r.hgetall(NAV_TARGETS)
    now = datetime.now(timezone.utc).timestamp()

    targets = []
    for label, val in raw.items():
        try:
            t = json.loads(val)
        except Exception:
            continue

        # Check cooldown
        import hashlib
        url_hash = hashlib.sha256(t.get("url", "").encode()).hexdigest()[:20]
        score = await r.zscore(NAV_COOLDOWN, url_hash)
        on_cooldown = bool(score and float(score) > now)
        next_visit_in = max(0, int(float(score) - now)) if score else 0

        targets.append({
            **t,
            "on_cooldown": on_cooldown,
            "next_visit_in_seconds": next_visit_in if on_cooldown else 0,
        })

    targets.sort(key=lambda x: (-x.get("priority", 5), x.get("label", "")))
    return {"count": len(targets), "targets": targets}


@router.post("/targets")
async def add_target(cfg: TargetConfig, r=Depends(get_redis)) -> dict:
    """Add or update a permanent knowledge source the navigator visits regularly."""
    payload = cfg.model_dump()
    await r.hset(NAV_TARGETS, cfg.label, json.dumps(payload))
    return {"status": "added", "label": cfg.label, "url": cfg.url}


@router.delete("/targets/{label}")
async def remove_target(label: str, r=Depends(get_redis)) -> dict:
    """Remove a knowledge source from the navigator's regular territory."""
    deleted = await r.hdel(NAV_TARGETS, label)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Target '{label}' not found")
    return {"status": "removed", "label": label}


@router.post("/targets/{label}/visit-now")
async def visit_now(label: str, r=Depends(get_redis)) -> dict:
    """Force an immediate visit to a configured target (clears its cooldown)."""
    raw = await r.hget(NAV_TARGETS, label)
    if not raw:
        raise HTTPException(status_code=404, detail=f"Target '{label}' not found")

    try:
        t = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=500, detail="Invalid target config")

    # Clear cooldown
    import hashlib
    url_hash = hashlib.sha256(t.get("url", "").encode()).hexdigest()[:20]
    await r.zrem(NAV_COOLDOWN, url_hash)

    # Push to front of queue
    await r.lpush(NAV_QUEUE, json.dumps(t))
    return {"status": "queued", "label": label, "url": t.get("url", "")}
