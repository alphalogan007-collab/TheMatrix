"""routes_source_seed.py — Source Mind seed-file loader.

Scans the mounted Y-Theory / Quran seed folders (read-only host paths) and
loads every .pdf / .txt / .md file into guidance:corpus.

Designed for MIND_ROLE=source only.  The cloud Worker learns from YouTube;
the local Source learns from the curated seed files.

Env vars:
  SEED_FILES_PATHS   colon-separated list of absolute paths inside the container
                     e.g. /seed/y-theory:/seed/corpus
                     default: /seed/y-theory:/seed/corpus
  REDIS_URL          (inherited from backend config)

Routes:
  POST /admin/source/seed-files          — scan + load, returns stats
  GET  /admin/source/seed-files/status   — corpus size + last-loaded info
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger("source_seed")

REDIS_URL       = os.environ.get("REDIS_URL", "redis://redis:6379/0")
_SEED_PATHS_ENV = os.environ.get("SEED_FILES_PATHS", "/seed/y-theory:/seed/corpus")
SUPPORTED_EXT   = {".pdf", ".txt", ".md"}


# ── helpers ──────────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    text = text.replace("\ufffd", " ").replace("\x00", "")
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"[\x80-\x9f]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_text_sync(path: Path) -> str:
    """Synchronous text extraction — always call via run_in_executor (CPU-bound)."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            parts = [page.extract_text() or "" for page in reader.pages]
            return _clean("\n\n".join(parts))
        except Exception as e:
            logger.warning("PDF extract failed %s: %s", path, e)
            return ""
    else:
        for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
            try:
                return _clean(path.read_text(encoding=enc))
            except UnicodeDecodeError:
                continue
        return ""


async def _extract_text(path: Path) -> str:
    """Non-blocking text extraction — PDF parsing runs in thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extract_text_sync, path)


def _file_id(path: Path, content: str) -> str:
    """Stable file_id: hash of (filename + first 1k chars of content)."""
    key = f"{path.name}::{content[:1000]}"
    return "seed_" + hashlib.sha1(key.encode("utf-8", errors="replace")).hexdigest()[:16]


def _collect_files() -> list[Path]:
    """Return all supported files across all configured seed paths."""
    files: list[Path] = []
    for raw_path in _SEED_PATHS_ENV.split(":"):
        p = Path(raw_path.strip())
        if not p.exists():
            continue
        for f in p.rglob("*"):
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXT:
                files.append(f)
    return files


# ── routes ───────────────────────────────────────────────────────────────────

@router.post("/admin/source/seed-files")
async def load_seed_files(force: bool = False):
    """Scan all configured seed paths and load files into guidance:corpus.

    Idempotent — already-present entries are skipped unless force=True.
    Returns counts of loaded, skipped, and errors.
    """
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    loaded = 0
    skipped = 0
    errors = 0
    loaded_titles: list[str] = []
    ts = datetime.now(timezone.utc).isoformat()

    try:
        files = _collect_files()
        for path in files:
            try:
                content = await _extract_text(path)
                if not content or len(content) < 50:
                    continue

                file_id = _file_id(path, content)

                if not force and await r.hexists("guidance:corpus", file_id):
                    skipped += 1
                    continue

                title = path.stem.replace("_", " ").replace("-", " ").title()
                record = json.dumps({
                    "file_id": file_id,
                    "title":   title[:300],
                    "content": content[:50_000],
                    "source":  f"seed_file:{path.name}",
                    "chars":   len(content),
                    "ts":      ts,
                })
                await r.hset("guidance:corpus", file_id, record)
                await r.sadd("guidance:index", file_id)
                await r.xadd(
                    "guidance:events",
                    {"file_id": file_id, "title": title, "chars": str(len(content)), "ts": ts},
                    maxlen=2000,
                )
                loaded += 1
                loaded_titles.append(title[:60])
            except Exception as e:
                logger.error("Failed to load %s: %s", path, e)
                errors += 1

        corpus_size = await r.hlen("guidance:corpus")

    finally:
        await r.aclose()

    logger.info("Seed load complete: loaded=%d skipped=%d errors=%d corpus_size=%d",
                loaded, skipped, errors, corpus_size)
    return {
        "loaded":       loaded,
        "skipped":      skipped,
        "errors":       errors,
        "corpus_size":  corpus_size,
        "paths_scanned": _SEED_PATHS_ENV.split(":"),
        "sample":       loaded_titles[:10],
    }


@router.get("/admin/source/seed-files/status")
async def seed_status():
    """Return current corpus size and configured seed paths."""
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        corpus_size = await r.hlen("guidance:corpus")
        paths = _SEED_PATHS_ENV.split(":")
        available = [p for p in paths if Path(p.strip()).exists()]
        loop = asyncio.get_event_loop()
        file_count = await loop.run_in_executor(None, lambda: sum(
            1 for p in available
            for f in Path(p.strip()).rglob("*")
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXT
        ))
    finally:
        await r.aclose()

    return {
        "corpus_size":    corpus_size,
        "seed_paths":     paths,
        "paths_available": available,
        "seed_file_count": file_count,
        "supported_ext":  list(SUPPORTED_EXT),
    }


# ── auto-load helper (called from lifespan) ──────────────────────────────────

async def auto_load_seed_files() -> dict[str, Any]:
    """Load seed files on startup (source role). Skips already-present entries."""
    files = _collect_files()
    if not files:
        logger.warning("auto_load_seed_files: no seed files found at %s", _SEED_PATHS_ENV)
        return {"loaded": 0, "skipped": 0, "errors": 0}

    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    loaded = skipped = errors = 0
    ts = datetime.now(timezone.utc).isoformat()
    try:
        for path in files:
            try:
                content = await _extract_text(path)  # non-blocking
                if not content or len(content) < 50:
                    continue
                file_id = _file_id(path, content)
                if await r.hexists("guidance:corpus", file_id):
                    skipped += 1
                    continue
                title = path.stem.replace("_", " ").replace("-", " ").title()
                await r.hset("guidance:corpus", file_id, json.dumps({
                    "file_id": file_id,
                    "title":   title[:300],
                    "content": content[:50_000],
                    "source":  f"seed_file:{path.name}",
                    "chars":   len(content),
                    "ts":      ts,
                }))
                await r.sadd("guidance:index", file_id)
                loaded += 1
            except Exception as e:
                logger.error("Seed load error %s: %s", path, e)
                errors += 1
    finally:
        await r.aclose()

    logger.info("Source seed auto-load: loaded=%d skipped=%d errors=%d files=%d",
                loaded, skipped, errors, len(files))
    return {"loaded": loaded, "skipped": skipped, "errors": errors}


async def start_event_relay(master_url: str) -> None:
    """Tail local spirit:events and forward new events to Prophet in near-real-time.

    Runs as a permanent background task on MIND_ROLE=source.
    Cursor persisted in Redis — restarts resume where they left off without
    replaying old events.  Only forwards events that arrived AFTER startup
    (cursor="$" on first run).
    """
    import httpx

    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    target = master_url.rstrip("/") + "/admin/events/relay"
    cursor_key = "source:relay:cursor"

    # First run: start from the CURRENT tip so we don't replay 33k old events.
    # On restart: resume from last acknowledged cursor stored in Redis.
    cursor = await r.get(cursor_key)
    if not cursor:
        # Resolve "$" → the actual last stream ID (required for non-blocking XREAD)
        latest = await r.xrevrange("spirit:events", "+", "-", count=1)
        cursor = latest[0][0] if latest else "0-0"
        await r.set(cursor_key, cursor)

    logger.info("Event relay started → %s  cursor=%s", target, cursor)

    # Brief startup delay — lets the event loop fully initialize before
    # making async Redis connections (avoids ThreadPoolExecutor loop errors).
    await asyncio.sleep(3)

    consecutive_failures = 0

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            while True:
                try:
                    # Non-blocking poll (no block= arg) — matches the rest of the codebase.
                    # asyncio.sleep provides the wait between polls.
                    msgs = await r.xread({"spirit:events": cursor}, count=50)
                    if not msgs:
                        await asyncio.sleep(2)
                        continue

                    batch: list[dict] = []
                    last_id = cursor
                    for _, entries in msgs:
                        for msg_id, fields in entries:
                            batch.append({"id": msg_id, **fields})
                            last_id = msg_id

                    if not batch:
                        continue

                    try:
                        resp = await client.post(target, json={"events": batch})
                        resp.raise_for_status()
                        # Only advance cursor after confirmed write
                        cursor = last_id
                        await r.set(cursor_key, cursor)
                        consecutive_failures = 0
                        logger.info("Relay → forwarded %d events to %s", len(batch), target)
                    except Exception as post_err:
                        consecutive_failures += 1
                        wait = min(60, 5 * consecutive_failures)
                        logger.warning("Relay POST failed (%d): %s — retry in %ds",
                                       consecutive_failures, post_err, wait)
                        await asyncio.sleep(wait)

                except asyncio.CancelledError:
                    break
                except Exception as read_err:
                    logger.warning("Relay read error: %s", read_err)
                    await asyncio.sleep(3)
    finally:
        try:
            await r.aclose()
        except Exception:
            pass
        logger.info("Event relay stopped")

