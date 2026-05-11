"""learn/guidance_scanner.py — Guidance file consumer.

Purpose:
  Watch guidance/inbox/ for new files.
  Extract raw text. Store in Redis as knowledge corpus.
  Move consumed files to guidance/completed/YYYY-MM-DD/.

  ZERO LLM calls — pure text extraction + Redis storage.
  No LLM budget needed for ingestion.

Supported formats:
  .pdf        — text extraction via pypdf
  .txt / .md  — read directly
  .url        — URL file (plain URL or Windows [InternetShortcut] format)
  .html       — HTML stripped to plain text
  .py         — Python source files (read as plain text — enables self-reflection)

Drop files in:    guidance/inbox/
Processed go to:  guidance/completed/YYYY-MM-DD/

Redis data:
  guidance:corpus   HASH    file_id → JSON {title, content, source, ts, chars}
  guidance:index    SET     consumed file_ids (dedup across container restarts)
  guidance:events   STREAM  one event per file consumed

Env vars:
  REDIS_URL
  GUIDANCE_INBOX      (default: /guidance/inbox)
  GUIDANCE_COMPLETED  (default: /guidance/completed)
  GUIDANCE_POLL_SECS  (default: 5)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import redis.asyncio as aioredis

# == Config ==================================================================
REDIS_URL  = os.environ["REDIS_URL"]
INBOX      = Path(os.environ.get("GUIDANCE_INBOX",      "/guidance/inbox"))
COMPLETED  = Path(os.environ.get("GUIDANCE_COMPLETED",  "/guidance/completed"))
POLL_SECS  = float(os.environ.get("GUIDANCE_POLL_SECS", "5"))

# GUIDANCE_SOURCES — colon-separated list of read-only source folders (Unix PATH convention).
# Files here are NEVER moved — they are permanent mounts (Y-Theory, Quran, etc.).
# The dedup index (guidance:index) prevents double-ingestion across restarts.
SOURCES: list[Path] = [
    Path(s.strip())
    for s in os.environ.get("GUIDANCE_SOURCES", "").split(":")
    if s.strip()
]

SUPPORTED = {".pdf", ".txt", ".md", ".url", ".link", ".html", ".py"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [GUIDANCE] %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("guidance")


# == Text extraction =========================================================

def _clean_text(text: str) -> str:
    """Remove non-printable / garbage characters from extracted text.

    Keeps: printable ASCII, common Unicode letters/punctuation, newlines, tabs.
    Strips: control characters (C0/C1), private-use, replacement chars, etc.
    """
    # Replace unicode replacement char and common garbage
    text = text.replace("\ufffd", " ").replace("\x00", "")
    # Strip C0 control chars except \t \n \r
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Strip C1 control chars (0x80-0x9F) and private-use area chars
    text = re.sub(r"[\x80-\x9f]", "", text)
    # Collapse 3+ blank lines → 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text and text.strip():
            pages.append(text.strip())
    raw = "\n\n".join(pages)
    return _clean_text(raw)


def _strip_html(html: str) -> str:
    # Remove script + style blocks
    html = re.sub(
        r"<(script|style|head)[^>]*>.*?</(script|style|head)>",
        "", html, flags=re.DOTALL | re.IGNORECASE,
    )
    # Convert block-level tags to newlines
    html = re.sub(r"<(br|p|div|li|h[1-6])[^>]*/?>", "\n", html, flags=re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Decode common HTML entities
    for ent, char in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                      ("&nbsp;", " "), ("&quot;", '"'), ("&#39;", "'")]:
        text = text.replace(ent, char)
    # Collapse whitespace
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_url_file(raw: str) -> str:
    """Handle plain URL or Windows [InternetShortcut] format."""
    for line in raw.split("\n"):
        line = line.strip()
        if line.upper().startswith("URL="):
            return line[4:].strip()
    # Fall back: first non-empty line
    for line in raw.split("\n"):
        line = line.strip()
        if line and not line.startswith("["):
            return line
    return raw.strip()


async def _fetch_url(url: str) -> tuple[str, str]:
    """Fetch URL content. Returns (title, text)."""
    async with httpx.AsyncClient(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": "MindAI-Guidance/1.0"},
    ) as client:
        r = await client.get(url)
        r.raise_for_status()

    ct = r.headers.get("content-type", "")
    if "html" in ct:
        # Try to extract <title>
        m = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.IGNORECASE | re.DOTALL)
        title = m.group(1).strip() if m else url
        content = _strip_html(r.text)
    else:
        title = url
        content = r.text

    return title, content


async def _extract(path: Path) -> tuple[str, str]:
    """Returns (title, content)."""
    suffix = path.suffix.lower()
    title  = path.stem

    if suffix == ".pdf":
        return title, _extract_pdf(path)

    if suffix in (".url", ".link"):
        raw = path.read_text(encoding="utf-8", errors="replace")
        url = _parse_url_file(raw)
        log.info("Fetching URL: %s", url)
        fetched_title, content = await _fetch_url(url)
        return fetched_title or title, content

    if suffix == ".html":
        return title, _clean_text(_strip_html(path.read_text(encoding="utf-8", errors="replace")))

    # .txt / .md / anything else
    return title, _clean_text(path.read_text(encoding="utf-8", errors="replace"))


# == Redis helpers ============================================================

async def _store(
    redis: aioredis.Redis,
    title: str,
    content: str,
    source: str,
    file_id: str,
) -> None:
    content_capped = content[:50_000]   # 50k chars max per file
    now = datetime.now(timezone.utc).isoformat()
    entry = json.dumps({
        "file_id": file_id,
        "title":   title[:300],
        "content": content_capped,
        "source":  source,
        "chars":   len(content),
        "ts":      now,
    })
    await redis.hset("guidance:corpus", file_id, entry)
    await redis.sadd("guidance:index", file_id)
    await redis.xadd(
        "guidance:events",
        {
            "file_id": file_id,
            "title":   title[:200],
            "source":  source,
            "chars":   str(len(content)),
            "ts":      now,
        },
        maxlen=1000,
    )


# == File mover ==============================================================

def _move_to_completed(path: Path) -> None:
    date_dir = COMPLETED / datetime.now(timezone.utc).strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    dest = date_dir / path.name
    if dest.exists():
        dest = date_dir / f"{path.stem}_{uuid.uuid4().hex[:6]}{path.suffix}"
    shutil.move(str(path), str(dest))
    log.info("Moved to completed: %s", dest.relative_to(COMPLETED))


# == Scanner loop ============================================================

async def _scan(redis: aioredis.Redis) -> None:
    if not INBOX.exists():
        INBOX.mkdir(parents=True, exist_ok=True)
    COMPLETED.mkdir(parents=True, exist_ok=True)

    paths = sorted(INBOX.iterdir())
    for path in paths:
        if path.is_dir():
            continue
        if path.name.startswith("."):
            continue
        if path.suffix.lower() not in SUPPORTED:
            log.debug("Unsupported file type, skipping: %s", path.name)
            continue

        # Stable file_id: hash of name + size + mtime
        stat   = path.stat()
        fid    = hashlib.sha256(
            f"{path.name}:{stat.st_size}:{stat.st_mtime:.0f}".encode()
        ).hexdigest()[:32]

        already = await redis.sismember("guidance:index", fid)
        if already:
            log.debug("Already consumed: %s — moving to completed", path.name)
            _move_to_completed(path)
            continue

        log.info("Consuming: %s", path.name)
        try:
            title, content = await _extract(path)
            content = content.strip()
            if not content:
                log.warning("No content extracted from: %s — skipping", path.name)
                _move_to_completed(path)
                continue

            await _store(redis, title, content, source=path.name, file_id=fid)
            log.info(
                "Stored: '%s' (%d chars) [%s]",
                title[:60], len(content), path.name,
            )
            _move_to_completed(path)

        except Exception as e:
            log.error("Failed to consume %s: %s", path.name, e)


# == Source folder scanner (read-only — never moves files) ==================

async def _scan_sources(redis: aioredis.Redis) -> None:
    """Scan GUIDANCE_SOURCES folders. Files are NEVER moved — permanent mounts.

    These are the unchanging source documents:
      - Y-Theory books (PDFs)
      - Quran Tafseer (PDFs)
      - DigitalWorld-Guidance (Code of Ethics, CEO letters)
      - Root seed files (faith, soul, universe, etc.)

    Dedup via guidance:index ensures each file is only ingested once,
    even across container restarts.
    """
    for source_root in SOURCES:
        if not source_root.exists():
            log.warning("Source folder not found: %s", source_root)
            continue

        folder_label = source_root.name
        all_files    = sorted(source_root.rglob("*"))

        for path in all_files:
            if not path.is_file():
                continue
            if path.name.startswith("."):
                continue
            if path.suffix.lower() not in SUPPORTED:
                continue

            # Stable dedup key: folder + name + size (mtime not used — mounts vary)
            stat = path.stat()
            fid  = hashlib.sha256(
                f"source:{folder_label}:{path.name}:{stat.st_size}".encode()
            ).hexdigest()[:32]

            already = await redis.sismember("guidance:index", fid)
            if already:
                continue  # already ingested — skip silently

            log.info("[source] Consuming: %s / %s", folder_label, path.name)
            try:
                title, content = await _extract(path)
                content = content.strip()
                if not content:
                    log.warning("[source] No content: %s — skipping", path.name)
                    # Mark as seen so we don't retry every cycle
                    await redis.sadd("guidance:index", fid)
                    continue

                source_label = f"{folder_label}:{path.name}"
                await _store(redis, title, content, source=source_label, file_id=fid)
                log.info(
                    "[source] Stored: '%s' (%d chars) [%s]",
                    title[:60], len(content), source_label,
                )

                # Small delay between large files to avoid Redis flooding
                await asyncio.sleep(0.1)

            except Exception as e:
                log.error("[source] Failed %s: %s", path.name, e)


# == Main ====================================================================

async def main() -> None:
    log.info("=== Guidance Scanner starting ===")
    log.info("Inbox:     %s", INBOX)
    log.info("Completed: %s", COMPLETED)
    log.info("Polling every %ss", POLL_SECS)
    if SOURCES:
        log.info("Source folders (%d):", len(SOURCES))
        for s in SOURCES:
            log.info("  %s", s)
    else:
        log.info("No GUIDANCE_SOURCES configured — inbox-only mode")

    redis = aioredis.from_url(REDIS_URL, decode_responses=True)

    log.info("Redis connected — watching for files...")
    while True:
        try:
            await _scan(redis)
        except Exception as e:
            log.error("Scan error: %s", e)

        # Scan source folders every cycle (dedup prevents re-ingestion)
        if SOURCES:
            try:
                await _scan_sources(redis)
            except Exception as e:
                log.error("Source scan error: %s", e)

        await asyncio.sleep(POLL_SECS)


if __name__ == "__main__":
    asyncio.run(main())
