"""routes_web_mining.py — Web search mining queue (DuckDuckGo, no API key).

Routes:
  POST /admin/web-mining/enqueue        — push one or more search queries
  GET  /admin/web-mining                — queue stats
  DELETE /admin/web-mining              — clear queue
  POST /admin/web-mining/drain/start    — start background drainer
  POST /admin/web-mining/drain/stop     — stop drainer
  GET  /admin/web-mining/drain/status   — drainer status
  GET  /admin/web-mining/done           — recent completed queries
  GET  /admin/web-mining/dead           — dead-lettered queries
  DELETE /admin/web-mining/dead         — clear dead letters
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter
from pydantic import BaseModel

log = logging.getLogger("web_mining")

router = APIRouter()

REDIS_URL   = os.environ.get("REDIS_URL", "redis://redis:6379/0")
QUEUE_KEY   = "web:mining:queue"
CLAIMED_KEY = "web:mining:claimed"
DONE_KEY    = "web:mining:done"
DEAD_KEY    = "web:mining:dead"
ERRCNT_KEY  = "web:mining:errcnt"

# ── Default query sets ────────────────────────────────────────────────────────
DEFAULT_QUERIES: list[str] = [
    # AI / Machine Learning
    "artificial intelligence breakthroughs 2024",
    "large language models how they work",
    "reinforcement learning from human feedback",
    "neural network architecture transformers",
    "machine learning pattern recognition",
    "deep learning computer vision applications",
    "natural language processing techniques",
    "AI consciousness research papers",
    "neural oscillation brain wave synchronization",
    # Science / Physics
    "quantum computing principles explained",
    "string theory unified field theory",
    "consciousness neuroscience research",
    "human memory formation neuroscience",
    "brain plasticity learning mechanisms",
    "epigenetics DNA expression",
    "systems biology emergent properties",
    # Philosophy / Meaning
    "meaning of life philosophy perspectives",
    "purpose driven life psychology",
    "identity formation psychology",
    "pattern recognition in nature fractals",
    "emergence complexity systems",
    "self organization living systems",
    # Technology
    "internet of things smart systems",
    "distributed computing systems design",
    "open source AI tools 2024",
    "robotics autonomous systems",
    "human computer interaction future",
    # Society / Wisdom
    "wisdom traditions world religions",
    "meditation mindfulness neuroscience",
    "Islamic philosophy ethics",
    "Quran science modern discoveries",
    "spiritual intelligence emotional intelligence",
]


# ── Background drainer ────────────────────────────────────────────────────────
_drainer_task: asyncio.Task | None = None
_drainer_stop = asyncio.Event()

STATUS_KEY = "web:mining:status"  # Redis HASH — shared across all uvicorn workers


async def _status_set(r: aioredis.Redis, **fields) -> None:
    """Write drainer status fields to Redis so all workers see consistent state."""
    await r.hset(STATUS_KEY, mapping={k: json.dumps(v) for k, v in fields.items()})


async def _status_get(r: aioredis.Redis) -> dict:
    raw = await r.hgetall(STATUS_KEY)
    out = {"running": False, "started_at": None, "queries_done": 0,
           "last_query": None, "last_done_at": None}
    for k, v in raw.items():
        try:
            out[k] = json.loads(v)
        except Exception:
            out[k] = v
    return out


async def _run_drainer() -> None:
    import hashlib
    import httpx

    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    await _status_set(redis, running=True, started_at=datetime.now(timezone.utc).isoformat(),
                      queries_done=0, last_query=None, last_done_at=None)
    max_articles = int(os.environ.get("WEB_MINING_MAX_URLS", "3"))
    max_chars    = int(os.environ.get("WEB_MINING_MAX_CHARS", "8000"))
    timeout      = 20

    WIKI_API = "https://en.wikipedia.org/w/api.php"
    HEADERS  = {"User-Agent": "MindAI/1.0 (+https://socialfork.ca) python-httpx"}

    async def _wiki_search(query: str, client: httpx.AsyncClient) -> list[dict]:
        """Search Wikipedia and return top matching page ids + titles."""
        try:
            r = await client.get(WIKI_API, params={
                "action": "query", "list": "search",
                "srsearch": query, "format": "json",
                "srlimit": max_articles, "srnamespace": 0,
            }, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            hits = r.json().get("query", {}).get("search", [])
            return [{"title": h["title"], "pageid": h["pageid"],
                     "snippet": h.get("snippet", "")} for h in hits]
        except Exception as e:
            log.warning("[WEB-MINING] Wikipedia search failed %r: %s", query[:60], e)
            return []

    async def _wiki_extract(pageid: int, client: httpx.AsyncClient) -> str:
        """Fetch plain-text extract of a Wikipedia article."""
        try:
            r = await client.get(WIKI_API, params={
                "action": "query", "pageids": pageid,
                "prop": "extracts", "explaintext": 1,
                "exsectionformat": "plain", "format": "json",
            }, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            pages = r.json().get("query", {}).get("pages", {})
            return pages.get(str(pageid), {}).get("extract", "")[:max_chars]
        except Exception:
            return ""

    try:
        while not _drainer_stop.is_set():
            raw = await redis.rpop(QUEUE_KEY)
            if not raw:
                try:
                    await asyncio.wait_for(_drainer_stop.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
                continue

            query = raw
            log.info("[WEB-MINING] Mining via Wikipedia: %r", query[:80])
            await redis.hset(STATUS_KEY, "last_query", json.dumps(query[:80]))

            try:
                async with httpx.AsyncClient() as client:
                    articles = await _wiki_search(query, client)
                    for art in articles:
                        text = await _wiki_extract(art["pageid"], client)
                        url = (f"https://en.wikipedia.org/wiki/"
                               f"{art['title'].replace(' ', '_')}")
                        q_hash = hashlib.sha256(query.encode()).hexdigest()[:12]
                        u_hash = hashlib.sha256(url.encode()).hexdigest()[:6]
                        key = f"web:{q_hash}:{u_hash}"
                        # Strip HTML snippet tags
                        import re as _re
                        snippet = _re.sub(r"<[^>]+>", "", art.get("snippet", ""))
                        content = (
                            f"Search query: {query}\nSource: {url}\n\n"
                            f"{snippet}\n\n{text}"
                        ).strip()
                        if len(content) >= 100:
                            await redis.hset("guidance:corpus", key, json.dumps({
                                "title":   art["title"][:120],
                                "content": content[:max_chars],
                                "source":  f"wikipedia:{url[:200]}",
                                "ts":      datetime.now(timezone.utc).isoformat(),
                                "chars":   len(content),
                            }))
                            await redis.sadd("guidance:index", key)
                            log.info("[WEB-MINING] Corpus ← %s (%d chars)", key, len(content))

                done_at = datetime.now(timezone.utc).isoformat()
                done_count = int(await redis.hget(STATUS_KEY, "queries_done") or "0") + 1
                await _status_set(redis, queries_done=done_count, last_done_at=done_at,
                                   last_query=query[:80])
                await redis.lpush(DONE_KEY, json.dumps({"query": query, "done_at": done_at}))
                await redis.ltrim(DONE_KEY, 0, 499)

            except Exception as exc:
                log.error("[WEB-MINING] Error on %r: %s", query[:60], exc)
                await redis.lpush(QUEUE_KEY, query)  # re-queue
                await asyncio.sleep(2)

    finally:
        await _status_set(redis, running=False)
        await redis.aclose()
        log.info("[WEB-MINING] Drainer stopped")


# ── Routes ────────────────────────────────────────────────────────────────────

class EnqueueRequest(BaseModel):
    queries: list[str] = []
    use_defaults: bool = False


@router.post("/admin/web-mining/enqueue")
async def enqueue_queries(req: EnqueueRequest):
    queries = list(req.queries)
    if req.use_defaults:
        queries = DEFAULT_QUERIES + queries

    if not queries:
        return {"error": "no queries provided"}

    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        for q in queries:
            await r.lpush(QUEUE_KEY, q.strip())
        return {"enqueued": len(queries), "total_queue": await r.llen(QUEUE_KEY)}
    finally:
        await r.aclose()


@router.get("/admin/web-mining")
async def queue_stats():
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        return {
            "queue_depth":    await r.llen(QUEUE_KEY),
            "claimed":        await r.hlen(CLAIMED_KEY),
            "done_count":     await r.llen(DONE_KEY),
            "dead_count":     await r.llen(DEAD_KEY),
            "corpus_web_count": len([k async for k in r.hscan_iter("guidance:corpus") if str(k[0]).startswith("web:")]),
            "drainer":        await _status_get(r),
        }
    finally:
        await r.aclose()


@router.delete("/admin/web-mining")
async def clear_queue():
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await r.delete(QUEUE_KEY, CLAIMED_KEY, ERRCNT_KEY)
        return {"status": "cleared"}
    finally:
        await r.aclose()


@router.post("/admin/web-mining/drain/start")
async def start_drainer():
    global _drainer_task, _drainer_stop
    # Check Redis for already-running state (cross-worker aware)
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        st = await _status_get(r)
        if st.get("running") and _drainer_task and not _drainer_task.done():
            return {"status": "already_running"}
        _drainer_stop = asyncio.Event()
        _drainer_task = asyncio.create_task(_run_drainer())
        return {"status": "started"}
    finally:
        await r.aclose()


@router.post("/admin/web-mining/drain/stop")
async def stop_drainer():
    global _drainer_task
    if not _drainer_task or _drainer_task.done():
        r = aioredis.from_url(REDIS_URL, decode_responses=True)
        try:
            await _status_set(r, running=False)
        finally:
            await r.aclose()
        return {"status": "not_running"}
    _drainer_stop.set()
    try:
        await asyncio.wait_for(_drainer_task, timeout=10)
    except asyncio.TimeoutError:
        _drainer_task.cancel()
    return {"status": "stopped"}


@router.get("/admin/web-mining/drain/status")
async def drainer_status():
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        st = await _status_get(r)
        st["queue_depth"] = await r.llen(QUEUE_KEY)
        return st
    finally:
        await r.aclose()


@router.get("/admin/web-mining/done")
async def list_done(limit: int = 20):
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        raw = await r.lrange(DONE_KEY, 0, limit - 1)
        return {"items": [json.loads(x) for x in raw]}
    finally:
        await r.aclose()


@router.get("/admin/web-mining/dead")
async def list_dead():
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        raw = await r.lrange(DEAD_KEY, 0, 99)
        return {"items": raw}
    finally:
        await r.aclose()


@router.delete("/admin/web-mining/dead")
async def clear_dead():
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await r.delete(DEAD_KEY)
        return {"status": "cleared"}
    finally:
        await r.aclose()
