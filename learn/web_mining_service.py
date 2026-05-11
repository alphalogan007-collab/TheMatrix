"""learn/web_mining_service.py — Web Search Mining (DuckDuckGo, no API key).

Mines web search results directly into guidance:corpus so all workers
immediately benefit from the knowledge without any LLM calls.

Flow:
  web:mining:queue (LIST) → pop query → DuckDuckGo search → fetch top URLs
  → extract text → write to guidance:corpus as web:{query_hash}:{i}

Redis keys:
  web:mining:queue        LIST  — pending search queries (LPUSH to add)
  web:mining:claimed      HASH  — query → {claimed_at}
  web:mining:done         LIST  — completed {query, urls, chars, done_at}
  web:mining:dead         LIST  — permanently failed queries
  web:mining:errcnt       HASH  — query → error_count

Env vars:
  REDIS_URL
  WEB_MINING_MAX_URLS     max URLs to fetch per query (default 3)
  WEB_MINING_MAX_CHARS    max chars extracted per URL (default 8000)
  WEB_MINING_POLL_SEC     poll interval when queue empty (default 5)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone

import httpx
import redis.asyncio as aioredis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WEB-MINING] %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("web_mining")

REDIS_URL        = os.environ.get("REDIS_URL", "redis://redis:6379/0")
MAX_URLS         = int(os.environ.get("WEB_MINING_MAX_URLS", "3"))
MAX_CHARS        = int(os.environ.get("WEB_MINING_MAX_CHARS", "8000"))
POLL_SEC         = float(os.environ.get("WEB_MINING_POLL_SEC", "5"))
MAX_RETRIES      = 3
TIMEOUT_SEC      = 15

QUEUE_KEY   = "web:mining:queue"
CLAIMED_KEY = "web:mining:claimed"
DONE_KEY    = "web:mining:done"
DEAD_KEY    = "web:mining:dead"
ERRCNT_KEY  = "web:mining:errcnt"

# ── HTML stripping ────────────────────────────────────────────────────────────

_TAG_RE   = re.compile(r"<[^>]+>")
_MULTI_NL = re.compile(r"\n{3,}")
_SCRIPT   = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_ENTITY   = re.compile(r"&[a-z]{2,6};|&#\d+;")


def _strip_html(html: str) -> str:
    text = _SCRIPT.sub(" ", html)
    text = _TAG_RE.sub(" ", text)
    text = _ENTITY.sub(" ", text)
    text = re.sub(r"\s+", " ", text)
    return _MULTI_NL.sub("\n\n", text).strip()


# ── DuckDuckGo search (no API key) ──────────────────────────────────────────

async def _ddg_search(query: str, client: httpx.AsyncClient) -> list[dict]:
    """Return list of {title, url, snippet} from DuckDuckGo HTML search."""
    try:
        resp = await client.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query, "kl": "us-en"},
            headers={"User-Agent": "MindAI/1.0 (+https://socialfork.ca)"},
            timeout=TIMEOUT_SEC,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as exc:
        log.warning("DDG search failed for %r: %s", query[:60], exc)
        return []

    html = resp.text
    results: list[dict] = []

    # Parse result links from DDG HTML format
    link_pattern = re.compile(
        r'<a class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )
    snippet_pattern = re.compile(
        r'<a class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )

    links   = link_pattern.findall(html)
    snippets = [m.group(1) for m in snippet_pattern.finditer(html)]

    for i, (url, title) in enumerate(links[:MAX_URLS + 3]):
        # Skip DDG internal / ad links
        if not url.startswith("http") or "duckduckgo.com" in url:
            continue
        snippet = _strip_html(snippets[i]) if i < len(snippets) else ""
        results.append({
            "url":     url,
            "title":   _strip_html(title)[:120],
            "snippet": snippet[:300],
        })
        if len(results) >= MAX_URLS:
            break

    log.info("DDG found %d results for %r", len(results), query[:60])
    return results


# ── URL text extraction ──────────────────────────────────────────────────────

async def _fetch_url_text(url: str, client: httpx.AsyncClient) -> str:
    """Fetch a URL and extract plain text. Returns empty string on failure."""
    try:
        resp = await client.get(
            url,
            headers={"User-Agent": "MindAI/1.0 (+https://socialfork.ca)"},
            timeout=TIMEOUT_SEC,
            follow_redirects=True,
        )
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        if "text" not in ct and "html" not in ct:
            return ""
        return _strip_html(resp.text)[:MAX_CHARS]
    except Exception as exc:
        log.debug("URL fetch failed %s: %s", url[:80], exc)
        return ""


# ── Corpus writer ─────────────────────────────────────────────────────────────

async def _write_to_corpus(
    redis: aioredis.Redis,
    query: str,
    result: dict,
    text: str,
) -> None:
    q_hash = hashlib.sha256(query.encode()).hexdigest()[:12]
    u_hash = hashlib.sha256(result["url"].encode()).hexdigest()[:6]
    key    = f"web:{q_hash}:{u_hash}"

    title   = result["title"] or query[:80]
    content = (
        f"Search query: {query}\n"
        f"Source: {result['url']}\n\n"
        f"{result['snippet']}\n\n"
        f"{text}"
    ).strip()

    if len(content) < 50:
        return

    await redis.hset("guidance:corpus", key, json.dumps({
        "title":   title[:120],
        "content": content[:MAX_CHARS],
        "source":  f"web:search:{result['url'][:200]}",
        "ts":      datetime.now(timezone.utc).isoformat(),
        "chars":   len(content),
    }))
    await redis.sadd("guidance:index", key)
    log.info("Corpus ← web: %s (%d chars)", key, len(content))


# ── Core mining loop ──────────────────────────────────────────────────────────

async def _mine_query(query: str, redis: aioredis.Redis) -> bool:
    """Mine one search query. Returns True on success."""
    async with httpx.AsyncClient() as client:
        results = await _ddg_search(query, client)
        if not results:
            log.warning("No DDG results for %r", query[:60])
            return False

        fetched = 0
        for result in results:
            text = await _fetch_url_text(result["url"], client)
            await _write_to_corpus(redis, query, result, text)
            fetched += 1

        # Record completion
        await redis.lpush(DONE_KEY, json.dumps({
            "query":    query,
            "urls":     fetched,
            "done_at":  datetime.now(timezone.utc).isoformat(),
        }))
        await redis.ltrim(DONE_KEY, 0, 499)  # keep last 500

    return True


async def _run(redis: aioredis.Redis) -> None:
    log.info("Web mining service started (max_urls=%d, max_chars=%d)", MAX_URLS, MAX_CHARS)

    while True:
        try:
            raw = await redis.rpop(QUEUE_KEY)
            if not raw:
                await asyncio.sleep(POLL_SEC)
                continue

            query = raw if isinstance(raw, str) else raw.decode()
            log.info("Mining query: %r", query[:80])

            # Track error count
            err_raw = await redis.hget(ERRCNT_KEY, query)
            err_cnt = int(err_raw) if err_raw else 0

            # Mark as claimed
            await redis.hset(CLAIMED_KEY, query, json.dumps({
                "claimed_at": datetime.now(timezone.utc).isoformat(),
            }))

            try:
                ok = await _mine_query(query, redis)
                if ok:
                    await redis.hdel(CLAIMED_KEY, query)
                    await redis.hdel(ERRCNT_KEY, query)
                else:
                    raise RuntimeError("No results returned")

            except Exception as exc:
                log.error("Mining failed for %r: %s", query[:60], exc)
                err_cnt += 1
                await redis.hset(ERRCNT_KEY, query, str(err_cnt))
                await redis.hdel(CLAIMED_KEY, query)

                if err_cnt >= MAX_RETRIES:
                    log.warning("Dead-lettering %r after %d errors", query[:60], err_cnt)
                    await redis.lpush(DEAD_KEY, query)
                    await redis.ltrim(DEAD_KEY, 0, 199)
                else:
                    # Re-queue for retry
                    await redis.lpush(QUEUE_KEY, query)

        except Exception as exc:
            log.error("Outer loop error: %s", exc)
            await asyncio.sleep(2)


async def main() -> None:
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await _run(redis)
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
