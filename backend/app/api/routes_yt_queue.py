"""routes_yt_queue.py — Distributed YouTube video queue for cloud minds.

Local (Master) pushes video URLs into a Redis list: yt:queue
Cloud minds (Slaves) atomically claim one URL at a time via RPOP.
When a mind finishes, it POSTs wisdom back via /admin/wisdom/sync.

Redis keys:
  yt:queue          LIST   — pending video URLs (LPUSH to add, RPOP to claim)
  yt:queue:claimed  HASH   — url → {mind_id, claimed_at, title}
  yt:queue:done     LIST   — completed url entries (LPUSH on sync)

Routes (Master — local):
  POST /admin/yt/queue/enqueue        — accept YT URL, enumerate videos, push all to queue
  GET  /admin/yt/queue                — inspect queue depth + claimed + done counts
  DELETE /admin/yt/queue              — clear the queue
  POST /admin/yt/queue/drain/start    — start server-side queue drainer
  POST /admin/yt/queue/drain/stop     — stop server-side queue drainer
  GET  /admin/yt/queue/drain/status   — drainer status

Routes (Slave — cloud minds):
  GET  /admin/yt/queue/claim     — atomically claim next video URL (RPOP)
  POST /admin/yt/queue/release   — return a URL to front of queue (on error)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger("yt_queue")

router = APIRouter()

REDIS_URL       = os.environ.get("REDIS_URL", "redis://redis:6379/0")
QUEUE_KEY       = "yt:queue"           # LIST of JSON {url, title, source_job}
CLAIMED_KEY     = "yt:queue:claimed"   # HASH url → JSON {mind_id, claimed_at}
DONE_KEY        = "yt:queue:done"      # LIST of JSON {url, title, mind_id, done_at}
DEAD_KEY        = "yt:queue:dead"      # LIST of JSON {url, title, errors, reason, dead_at}
ERROR_COUNT_KEY = "yt:queue:errcnt"   # HASH url → error_count
MAX_RETRIES     = 3                    # permanent failure after this many attempts


# ── helpers ───────────────────────────────────────────────────────────────────

def _collect_urls(url: str) -> list[dict]:
    """Use yt-dlp flat extraction to get all video URLs from a playlist/channel/single."""
    import yt_dlp

    # Channel URL → /videos
    channel_m = re.search(
        r"youtube\.com/((?:@|channel/|c/|user/)[^/?#&]+)", url
    )
    if channel_m:
        handle = channel_m.group(1).rstrip("/")
        url = f"https://www.youtube.com/{handle}/videos"
        is_playlist = True
    else:
        list_m = re.search(r"[?&]list=([A-Za-z0-9_-]+)", url)
        if list_m:
            url = f"https://www.youtube.com/playlist?list={list_m.group(1)}"
            is_playlist = True
        else:
            is_playlist = False

    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": is_playlist,
        "noplaylist": not is_playlist,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if is_playlist and "entries" in info:
        return [
            {
                "url": (
                    e.get("webpage_url")
                    or e.get("url")
                    or f"https://www.youtube.com/watch?v={e.get('id','')}"
                ),
                "title": e.get("title") or e.get("id") or "?",
            }
            for e in (info.get("entries") or [])
            if e
        ]
    return [{
        "url": info.get("webpage_url") or info.get("original_url") or url,
        "title": info.get("title") or "?",
    }]


async def _redis() -> aioredis.Redis:
    return aioredis.from_url(REDIS_URL, decode_responses=True)


# ── models ────────────────────────────────────────────────────────────────────

class EnqueueBody(BaseModel):
    url: str          # YouTube URL (single video, playlist, or channel)

class ReleaseBody(BaseModel):
    url: str
    mind_id: str
    error: str = ""


# ── routes ────────────────────────────────────────────────────────────────────

@router.post("/admin/yt/queue/enqueue")
async def yt_queue_enqueue(body: EnqueueBody):
    """Enumerate all videos at the given URL and push each to yt:queue."""
    if not body.url.strip():
        raise HTTPException(status_code=400, detail="url required")

    import asyncio
    loop = asyncio.get_event_loop()
    try:
        entries = await loop.run_in_executor(None, _collect_urls, body.url.strip())
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    r = await _redis()
    try:
        pushed = 0
        for e in entries:
            item = json.dumps({
                "url":       e["url"],
                "title":     e["title"],
                "queued_at": datetime.now(timezone.utc).isoformat(),
                # No corpus snapshot — slaves pull live state from
                # GET /admin/mind/broadcast on the master at claim time.
                # Local mind is the source; slaves listen to it, not a frozen copy.
            })
            await r.lpush(QUEUE_KEY, item)
            pushed += 1
        return {
            "queued": pushed,
            "total_pending": await r.llen(QUEUE_KEY),
            "sample": entries[:3],
        }
    finally:
        await r.aclose()


@router.get("/admin/yt/queue")
async def yt_queue_status():
    """Return queue depth, claimed count, and done count."""
    r = await _redis()
    try:
        pending  = await r.llen(QUEUE_KEY)
        claimed  = await r.hlen(CLAIMED_KEY)
        done     = await r.llen(DONE_KEY)
        # Peek top 10 pending
        raw_top  = await r.lrange(QUEUE_KEY, -10, -1)  # -1=rightmost = next to claim
        top = [json.loads(x) for x in reversed(raw_top)]
        return {
            "pending": pending,
            "claimed": claimed,
            "done":    done,
            "next_10": top,
        }
    finally:
        await r.aclose()


@router.get("/admin/yt/queue/claim")
async def yt_queue_claim(mind_id: str = ""):
    """Atomically claim the next pending video.  Returns the video entry or 204."""
    if not mind_id:
        mind_id = uuid.uuid4().hex[:12]

    r = await _redis()
    try:
        raw = await r.rpop(QUEUE_KEY)
        if not raw:
            return {"claimed": False, "message": "queue empty"}

        entry = json.loads(raw)
        claim_record = json.dumps({
            "mind_id":    mind_id,
            "title":      entry.get("title", "?"),
            "claimed_at": datetime.now(timezone.utc).isoformat(),
        })
        await r.hset(CLAIMED_KEY, entry["url"], claim_record)
        return {
            "claimed":   True,
            "mind_id":   mind_id,
            "url":       entry["url"],
            "title":     entry.get("title", "?"),
            "remaining": await r.llen(QUEUE_KEY),
            # Slave must now call GET /admin/mind/broadcast on MASTER_URL
            # to receive the live source state before processing.
        }
    finally:
        await r.aclose()


@router.post("/admin/yt/queue/release")
async def yt_queue_release(body: ReleaseBody):
    """Return a URL to the front of the queue (on processing error)."""
    r = await _redis()
    try:
        # Remove from claimed
        await r.hdel(CLAIMED_KEY, body.url)
        # Get original title from claimed record if available
        raw_claim = await r.hget(CLAIMED_KEY, body.url)
        title = "?"
        if raw_claim:
            title = json.loads(raw_claim).get("title", "?")
        # Push back to right side (will be claimed next)
        item = json.dumps({
            "url":   body.url,
            "title": title,
            "queued_at": datetime.now(timezone.utc).isoformat(),
            "release_reason": body.error,
        })
        await r.rpush(QUEUE_KEY, item)
        return {"released": True, "url": body.url, "pending": await r.llen(QUEUE_KEY)}
    finally:
        await r.aclose()


@router.delete("/admin/yt/queue")
async def yt_queue_clear():
    """Clear the pending queue (claimed and done are preserved)."""
    r = await _redis()
    try:
        count = await r.llen(QUEUE_KEY)
        await r.delete(QUEUE_KEY)
        return {"cleared": count}
    finally:
        await r.aclose()


# ── server-side queue drainer ─────────────────────────────────────────────────
# Runs as a persistent asyncio task inside the uvicorn process.
# Claims one video at a time from yt:queue, extracts subtitles/transcript via
# yt-dlp, and pushes the content to seed:input for topology processing.

_drain_task: asyncio.Task | None = None
_drain_running: bool = False
_drain_stats: dict[str, Any] = {
    "started_at": None,
    "processed": 0,
    "errors": 0,
    "current_url": None,
    "current_title": None,
    "last_done_at": None,
}
_drain_sem: asyncio.Semaphore | None = None


def _get_drain_sem() -> asyncio.Semaphore:
    global _drain_sem
    if _drain_sem is None:
        _drain_sem = asyncio.Semaphore(1)
    return _drain_sem


def _vtt_to_text(vtt: str) -> str:
    """Strip WEBVTT/SRT cue formatting → plain text."""
    text = re.sub(r"^WEBVTT[^\n]*\n+", "", vtt, flags=re.MULTILINE)
    text = re.sub(r"\d[\d:]+\.?\d*\s*-->\s*\d[\d:]+\.?\d*[^\n]*\n", "", text)
    text = re.sub(r"^\d+\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_video_sync(vid_url: str, tmp_dir: str) -> tuple[dict, str]:
    """Synchronous yt-dlp call: download subtitles for one video."""
    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en"],
        "subtitlesformat": "vtt",
        "outtmpl": str(Path(tmp_dir) / "%(id)s.%(ext)s"),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(vid_url, download=True) or {}

    sub_text = ""
    for f in Path(tmp_dir).iterdir():
        if f.suffix in (".vtt", ".srt") and f.stat().st_size > 0:
            raw = f.read_text(encoding="utf-8", errors="replace")
            sub_text = _vtt_to_text(raw)
            break

    return info, sub_text


async def _dead_letter(r: aioredis.Redis, url: str, title: str, reason: str, errors: int) -> None:
    """Move a URL to the dead-letter queue — never retried again."""
    dead_item = json.dumps({
        "url":     url,
        "title":   title,
        "errors":  errors,
        "reason":  reason[:500],
        "dead_at": datetime.now(timezone.utc).isoformat(),
    })
    await r.lpush(DEAD_KEY, dead_item)
    await r.ltrim(DEAD_KEY, 0, 4_999)
    await r.hdel(CLAIMED_KEY, url)
    await r.hdel(ERROR_COUNT_KEY, url)
    log.warning("dead-lettered after %d errors: %s — %s", errors, title[:60], reason[:120])


async def _drain_one(r: aioredis.Redis, entry: dict) -> bool:
    """Extract and push one video entry. Returns True on success."""
    url   = entry.get("url", "")
    title = entry.get("title", "?")
    _drain_stats["current_url"]   = url
    _drain_stats["current_title"] = title

    loop = asyncio.get_event_loop()
    try:
        async with _get_drain_sem():
            with tempfile.TemporaryDirectory() as tmp:
                info, sub_text = await loop.run_in_executor(
                    None, _extract_video_sync, url, tmp
                )
    except Exception as exc:
        err_msg = str(exc)
        # Increment per-URL error count
        new_count = await r.hincrby(ERROR_COUNT_KEY, url, 1)
        log.warning("drain error #%d/%d %s: %s", new_count, MAX_RETRIES, url, err_msg[:120])

        if new_count >= MAX_RETRIES:
            # Permanent failure — dead-letter, never re-queue
            await _dead_letter(r, url, title, err_msg, new_count)
        else:
            # Temporary failure — re-queue with exponential backoff delay
            backoff = 30 * (2 ** (new_count - 1))  # 30s, 60s, 120s
            log.info("will retry in %ds (attempt %d/%d)", backoff, new_count, MAX_RETRIES)
            release_item = json.dumps({
                "url":            url,
                "title":          title,
                "queued_at":      datetime.now(timezone.utc).isoformat(),
                "release_reason": err_msg[:300],
                "retry_attempt":  new_count,
            })
            await asyncio.sleep(backoff)
            await r.rpush(QUEUE_KEY, release_item)
            await r.hdel(CLAIMED_KEY, url)
        return False

    # Build content
    parts = [f"Title: {info.get('title') or title}"]
    if info.get("channel"):
        parts.append(f"Channel: {info['channel']}")
    if info.get("upload_date"):
        parts.append(f"Date: {info['upload_date']}")
    if info.get("webpage_url"):
        parts.append(f"URL: {info['webpage_url']}")
    if info.get("description"):
        parts.append(f"\nDescription:\n{info['description'][:2000]}")
    if sub_text:
        parts.append(f"\nTranscript:\n{sub_text}")
    content = "\n".join(parts).strip()

    if not content:
        log.info("drain: no content for %s, skipping", url)
        _mark_done(entry, info)
        await r.hdel(CLAIMED_KEY, url)
        return True

    # Push to seed:input
    session_id = uuid.uuid4().hex
    await r.xadd(
        "seed:input",
        {
            "input_type": "text",
            "content": content[:50_000],
            "source": f"yt_drain:{url}",
            "session_id": session_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "origin": "yt_queue_drain",
        },
        maxlen=50_000,
    )

    done_item = json.dumps({
        "url": url,
        "title": info.get("title") or title,
        "chars": len(content),
        "done_at": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
    })
    await r.lpush(DONE_KEY, done_item)
    await r.ltrim(DONE_KEY, 0, 9_999)
    await r.hdel(CLAIMED_KEY, url)

    # Emit a spirit:events pulse so the world viewer shows activity
    ts_now = datetime.now(timezone.utc).isoformat()
    domain = "space"
    layer_num = min(8, max(1, (len(content) // 5000) + 1))  # depth = content richness
    await r.xadd(
        "spirit:events",
        {
            "type":       "layer_done",
            "mind_name":  f"{domain}_layer{layer_num}",
            "layer_num":  str(layer_num),
            "layer":      f"{domain}:layer{layer_num}",
            "ts":         ts_now,
            "session_id": session_id,
            "topic":      f"yt_drain:{title[:120]}",
            "direction":  "descending",
            "output":     f"[YT Absorbed]\nTitle: {(info.get('title') or title)[:200]}\nURL: {url}\nChars: {len(content)}\n[affinity={min(99.0, len(content)/500):.4f}]",
        },
        maxlen=50_000,
    )

    _drain_stats["processed"] += 1
    _drain_stats["last_done_at"] = datetime.now(timezone.utc).isoformat()
    log.info("drain ✓ %s (%d chars)", title[:60], len(content))
    return True


def _mark_done(entry: dict, info: dict) -> None:
    pass  # used for no-content case, logging only


async def _drain_loop() -> None:
    """Background loop: drain yt:queue one video at a time.

    Cost-safety rules:
    - MAX_RETRIES per URL: dead-lettered after 3 failures, never retried again
    - Exponential backoff on retry (30s / 60s / 120s)
    - 3s pause between successful videos (rate-limit courtesy)
    - Already-dead URLs are skipped immediately on claim
    """
    global _drain_running
    log.info("Queue drainer started (MAX_RETRIES=%d)", MAX_RETRIES)
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        while _drain_running:
            raw = await r.rpop(QUEUE_KEY)
            if not raw:
                await asyncio.sleep(30)
                continue

            try:
                entry = json.loads(raw)
            except Exception:
                continue

            url = entry.get("url", "")

            # Skip if already dead-lettered (URL somehow re-appeared)
            existing_errors = int(await r.hget(ERROR_COUNT_KEY, url) or 0)
            if existing_errors >= MAX_RETRIES:
                log.info("skipping already-failed url: %s", url)
                await _dead_letter(r, url, entry.get("title", "?"),
                                   "skipped: already exceeded max retries", existing_errors)
                continue

            # Mark claimed
            claim_record = json.dumps({
                "mind_id":    "server_drain",
                "title":      entry.get("title", "?"),
                "claimed_at": datetime.now(timezone.utc).isoformat(),
                "attempt":    existing_errors + 1,
            })
            await r.hset(CLAIMED_KEY, url, claim_record)

            try:
                ok = await _drain_one(r, entry)
                if ok:
                    # Clear error count on success
                    await r.hdel(ERROR_COUNT_KEY, url)
                else:
                    _drain_stats["errors"] += 1
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("drain loop unhandled error: %s", exc)
                _drain_stats["errors"] += 1

            # Pause between videos (rate-limit courtesy, only on success)
            if _drain_running:
                await asyncio.sleep(3)
    finally:
        _drain_stats["current_url"]   = None
        _drain_stats["current_title"] = None
        await r.aclose()
        log.info("Queue drainer stopped (processed=%d errors=%d)",
                 _drain_stats["processed"], _drain_stats["errors"])


async def _ensure_drain_running() -> None:
    """Start the drainer if not already running. Safe to call from lifespan."""
    global _drain_task, _drain_running
    if _drain_task and not _drain_task.done():
        return
    _drain_running = True
    _drain_stats["started_at"] = datetime.now(timezone.utc).isoformat()
    _drain_stats["processed"]  = 0
    _drain_stats["errors"]     = 0
    _drain_task = asyncio.create_task(_drain_loop())


@router.post("/admin/yt/queue/drain/start")
async def drain_start():
    """Start the server-side queue drainer background task."""
    global _drain_task, _drain_running
    if _drain_task and not _drain_task.done():
        return {"started": False, "message": "already running"}
    _drain_running = True
    _drain_stats["started_at"] = datetime.now(timezone.utc).isoformat()
    _drain_stats["processed"]  = 0
    _drain_stats["errors"]     = 0
    _drain_task = asyncio.create_task(_drain_loop())
    return {"started": True, "message": "queue drainer started"}


@router.post("/admin/yt/queue/drain/stop")
async def drain_stop():
    """Stop the server-side queue drainer."""
    global _drain_running, _drain_task
    _drain_running = False
    if _drain_task and not _drain_task.done():
        _drain_task.cancel()
    return {"stopped": True, "stats": _drain_stats}


@router.get("/admin/yt/queue/drain/status")
async def drain_status():
    """Return drainer status and stats."""
    r = await _redis()
    try:
        pending    = await r.llen(QUEUE_KEY)
        done       = await r.llen(DONE_KEY)
        dead       = await r.llen(DEAD_KEY)
        err_counts = await r.hgetall(ERROR_COUNT_KEY)
    finally:
        await r.aclose()
    return {
        "running":      _drain_running and bool(_drain_task and not _drain_task.done()),
        "stats":        _drain_stats,
        "pending":      pending,
        "done":         done,
        "dead_letters": dead,
        "max_retries":  MAX_RETRIES,
        "per_url_errors": {url: int(cnt) for url, cnt in err_counts.items()},
    }


@router.get("/admin/yt/queue/dead")
async def yt_queue_dead(count: int = 50):
    """List the most recent dead-lettered videos (failed after MAX_RETRIES)."""
    r = await _redis()
    try:
        raw_items = await r.lrange(DEAD_KEY, 0, count - 1)
    finally:
        await r.aclose()
    items = []
    for raw in raw_items:
        try:
            items.append(json.loads(raw))
        except Exception:
            pass
    return {"dead_letters": items, "total": len(items), "max_retries": MAX_RETRIES}


class DeadLetterBody(BaseModel):
    url: str
    reason: str = "manual"


@router.post("/admin/yt/queue/dead-letter")
async def yt_queue_force_dead(body: DeadLetterBody):
    """Manually dead-letter a URL — removes it from queue/claimed and bans future retry.
    Use this to immediately stop retrying a bot-blocked or broken video.
    """
    r = await _redis()
    try:
        # Remove from claimed
        await r.hdel(CLAIMED_KEY, body.url)
        # Set error count at MAX so drain_loop will also skip it if it pops out
        await r.hset(ERROR_COUNT_KEY, body.url, MAX_RETRIES)
        # Remove from pending queue (scan and rebuild without this URL)
        raw_all = await r.lrange(QUEUE_KEY, 0, -1)
        filtered = [x for x in raw_all if body.url not in x]
        removed = len(raw_all) - len(filtered)
        if removed:
            await r.delete(QUEUE_KEY)
            for item in filtered:
                await r.lpush(QUEUE_KEY, item)
        # Write to dead-letter list
        await _dead_letter(r, body.url, "?", body.reason, MAX_RETRIES)
    finally:
        await r.aclose()
    return {
        "dead_lettered": True,
        "url": body.url,
        "removed_from_queue": removed,
        "reason": body.reason,
    }


@router.delete("/admin/yt/queue/dead")
async def yt_queue_clear_dead():
    """Clear the dead-letter queue and reset all per-URL error counts."""
    r = await _redis()
    try:
        dead_count = await r.llen(DEAD_KEY)
        await r.delete(DEAD_KEY)
        await r.delete(ERROR_COUNT_KEY)
    finally:
        await r.aclose()
    return {"cleared_dead_letters": dead_count}
