"""routes_monitor.py — Real-time health and processing stats.

GET /monitor/stats   — full system snapshot
GET /monitor/angels  — per-angel entry counts
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import asyncpg
from fastapi import APIRouter

from app.config import get_settings

router = APIRouter()

_start_time = time.time()

# Cache: return instantly on every browser poll — refresh in background
_stats_cache: dict = {}
_stats_cache_ts: float = 0.0
_stats_refreshing: bool = False
_STATS_TTL = 8.0  # seconds


async def _fetch_stats_from_db() -> dict:
    """Open a direct asyncpg connection (bypasses SQLAlchemy pool) with hard timeout."""
    settings = get_settings()
    # Convert SQLAlchemy URL → asyncpg DSN
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")

    db_ok = False
    total_entries = -1
    recent_entries = -1
    angel_counts: dict = {}
    category_counts: dict = {}
    last_entry_at = None

    try:
        conn = await asyncio.wait_for(asyncpg.connect(dsn), timeout=5.0)
        try:
            db_ok = True

            total_entries = await asyncio.wait_for(
                conn.fetchval("SELECT COUNT(*) FROM seed_mind_memory_entries"), timeout=4.0
            ) or 0

            recent_entries = await asyncio.wait_for(
                conn.fetchval(
                    "SELECT COUNT(*) FROM seed_mind_memory_entries "
                    "WHERE created_at >= NOW() - INTERVAL '60 seconds'"
                ), timeout=4.0
            ) or 0

            rows = await asyncio.wait_for(
                conn.fetch(
                    "SELECT mind_name, COUNT(*) AS cnt FROM seed_mind_memory_entries "
                    "GROUP BY mind_name ORDER BY cnt DESC LIMIT 20"
                ), timeout=4.0
            )
            angel_counts = {r["mind_name"]: r["cnt"] for r in rows}

            rows = await asyncio.wait_for(
                conn.fetch(
                    "SELECT category, COUNT(*) AS cnt FROM seed_mind_memory_entries "
                    "GROUP BY category ORDER BY cnt DESC LIMIT 10"
                ), timeout=4.0
            )
            category_counts = {r["category"]: r["cnt"] for r in rows}

            row = await asyncio.wait_for(
                conn.fetchrow(
                    "SELECT created_at FROM seed_mind_memory_entries "
                    "ORDER BY created_at DESC LIMIT 1"
                ), timeout=4.0
            )
            last_entry_at = row["created_at"].isoformat() if row else None

        finally:
            await conn.close()

    except Exception:
        pass  # return whatever was collected

    return {
        "ok":             db_ok,
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": int(time.time() - _start_time),
        "database": {
            "connected":     db_ok,
            "total_entries": total_entries,
            "recent_60s":    recent_entries,
            "last_entry_at": last_entry_at,
        },
        "angels":     angel_counts,
        "categories": category_counts,
    }


async def _refresh_cache() -> None:
    global _stats_cache, _stats_cache_ts, _stats_refreshing
    _stats_refreshing = True
    try:
        result = await _fetch_stats_from_db()
        _stats_cache = result
        _stats_cache_ts = time.time()
    except Exception:
        pass
    finally:
        _stats_refreshing = False


@router.get("/monitor/stats")
async def monitor_stats() -> dict:
    """Return cached stats instantly; refresh in background every 8s."""
    global _stats_refreshing

    now = time.time()
    cache_stale = (now - _stats_cache_ts) >= _STATS_TTL

    # Kick off background refresh if cache is stale and not already refreshing
    if cache_stale and not _stats_refreshing:
        asyncio.create_task(_refresh_cache())

    # Return cache immediately (even if first call — returns empty dict briefly)
    if _stats_cache:
        return _stats_cache

    # First-ever call: wait for refresh to complete (max 10s)
    await _refresh_cache()
    return _stats_cache or {
        "ok": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": int(time.time() - _start_time),
        "database": {"connected": False, "total_entries": 0, "recent_60s": 0, "last_entry_at": None},
        "angels": {},
        "categories": {},
    }


@router.get("/monitor/angels")
async def monitor_angels() -> dict:
    """Quick per-angel entry counts — served from cache."""
    if _stats_cache:
        return {"angels": _stats_cache.get("angels", {})}
    return {"angels": {}}
