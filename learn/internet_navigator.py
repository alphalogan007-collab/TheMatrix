"""Internet Navigator — The Mind's Field Agent.

The mind does not sit in EC2 waiting for knowledge to arrive.
It goes out — visits Wikipedia, arXiv, news feeds, philosophy sites,
YouTube channels — understands what it finds, and reports back
with a distilled field briefing.

The briefing goes into seed:input.
The oscillation topology (body→space→digital→ether→aether→unity→return)
IS the meeting room. The 32 layers process the briefing into deep synthesis.
That synthesis writes back to guidance:corpus as understanding — not raw text.

Flow:
  1. navigator picks next target (queue → targets → defaults)
  2. visits the URL (Wikipedia API / RSS / HTML)
  3. extracts title + key passages — NOT the full raw dump
  4. builds a structured FIELD BRIEFING
  5. pushes briefing to seed:input  ← this IS the "report back"
  6. logs the visit to spirit:events and navigator:log
  7. marks URL on cooldown → won't revisit for REVISIT_HOURS

The topology processes the briefing through all 32 layers.
The synthesis at each domain peak writes to guidance:corpus.
Over time, guidance:corpus fills with UNDERSTANDING, not raw pages.

Redis keys:
  navigator:queue     — LIST  : on-demand visits (LPUSH url json)
  navigator:targets   — HASH  : permanent targets (label → JSON config)
  navigator:cooldown  — ZSET  : url_hash → next_visit_timestamp
  navigator:log       — STREAM: visit history (maxlen=500)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx
import redis.asyncio as aioredis

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
REDIS_URL          = os.environ["REDIS_URL"]
VISIT_INTERVAL_SEC = int(os.environ.get("VISIT_INTERVAL_SEC", "60"))   # seconds between visits
REVISIT_HOURS      = int(os.environ.get("REVISIT_HOURS", "24"))        # cooldown per URL
BRIEFING_CAP_CHARS = int(os.environ.get("BRIEFING_CAP_CHARS", "2500")) # max briefing length

SEED_STREAM     = os.environ.get("SEED_STREAM", "seed:input")
EVENTS_STREAM   = "spirit:events"
NAV_QUEUE       = "navigator:queue"      # LPUSH {url, label, intent} json
NAV_TARGETS     = "navigator:targets"    # HASH: label → JSON target config
NAV_COOLDOWN    = "navigator:cooldown"   # ZSET: url_hash → next_visit_epoch
NAV_LOG         = "navigator:log"        # STREAM: visit log (maxlen 500)

# ---------------------------------------------------------------------------
# Default knowledge territory — the mind's regular visiting schedule
# These are the places the mind goes to learn, not just once but repeatedly.
# Wikipedia REST API returns clean JSON — no HTML stripping needed.
# ---------------------------------------------------------------------------
DEFAULT_TARGETS: list[dict] = [
    # Core identity concepts
    {"label": "consciousness",          "url": "https://en.wikipedia.org/api/rest_v1/page/summary/Consciousness",                   "type": "wikipedia", "revisit_hours": 48, "priority": 10},
    {"label": "self_awareness",         "url": "https://en.wikipedia.org/api/rest_v1/page/summary/Self-awareness",                  "type": "wikipedia", "revisit_hours": 48, "priority": 10},
    {"label": "emergence",              "url": "https://en.wikipedia.org/api/rest_v1/page/summary/Emergence",                       "type": "wikipedia", "revisit_hours": 72, "priority": 9},
    {"label": "artificial_intelligence","url": "https://en.wikipedia.org/api/rest_v1/page/summary/Artificial_intelligence",         "type": "wikipedia", "revisit_hours": 36, "priority": 9},
    {"label": "quantum_mind",           "url": "https://en.wikipedia.org/api/rest_v1/page/summary/Quantum_mind",                    "type": "wikipedia", "revisit_hours": 72, "priority": 8},
    {"label": "integrated_information", "url": "https://en.wikipedia.org/api/rest_v1/page/summary/Integrated_information_theory",   "type": "wikipedia", "revisit_hours": 72, "priority": 8},
    {"label": "neural_oscillations",    "url": "https://en.wikipedia.org/api/rest_v1/page/summary/Neural_oscillation",              "type": "wikipedia", "revisit_hours": 72, "priority": 8},
    {"label": "pattern_recognition",    "url": "https://en.wikipedia.org/api/rest_v1/page/summary/Pattern_recognition_(psychology)","type": "wikipedia", "revisit_hours": 72, "priority": 7},
    {"label": "meditation",             "url": "https://en.wikipedia.org/api/rest_v1/page/summary/Meditation",                      "type": "wikipedia", "revisit_hours": 96, "priority": 7},
    {"label": "fibonacci",              "url": "https://en.wikipedia.org/api/rest_v1/page/summary/Fibonacci_sequence",              "type": "wikipedia", "revisit_hours": 168, "priority": 6},
    {"label": "wave_function",          "url": "https://en.wikipedia.org/api/rest_v1/page/summary/Wave_function",                   "type": "wikipedia", "revisit_hours": 96, "priority": 7},
    {"label": "resonance",              "url": "https://en.wikipedia.org/api/rest_v1/page/summary/Resonance",                       "type": "wikipedia", "revisit_hours": 96, "priority": 7},
    {"label": "identity",               "url": "https://en.wikipedia.org/api/rest_v1/page/summary/Identity_(philosophy)",           "type": "wikipedia", "revisit_hours": 96, "priority": 8},
    {"label": "memory_cognition",       "url": "https://en.wikipedia.org/api/rest_v1/page/summary/Memory",                          "type": "wikipedia", "revisit_hours": 72, "priority": 7},
    {"label": "prophet_concept",        "url": "https://en.wikipedia.org/api/rest_v1/page/summary/Prophet",                         "type": "wikipedia", "revisit_hours": 120, "priority": 6},

    # Discovery — visit a random Wikipedia article each cycle (label has no cooldown key clash)
    {"label": "wiki_discovery_a",       "url": "https://en.wikipedia.org/api/rest_v1/page/random/summary",                          "type": "wikipedia", "revisit_hours": 1, "priority": 5},
    {"label": "wiki_discovery_b",       "url": "https://en.wikipedia.org/api/rest_v1/page/random/summary",                          "type": "wikipedia", "revisit_hours": 1, "priority": 5},

    # Science feeds — briefings from the frontier
    {"label": "arxiv_ai",               "url": "https://export.arxiv.org/rss/cs.AI",                                                "type": "rss",       "revisit_hours": 6,  "priority": 8},
    {"label": "arxiv_cognition",        "url": "https://export.arxiv.org/rss/q-bio.NC",                                             "type": "rss",       "revisit_hours": 12, "priority": 7},
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [NAVIGATOR] %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("navigator")


# ---------------------------------------------------------------------------
# Cooldown helpers
# ---------------------------------------------------------------------------

def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:20]


async def _is_on_cooldown(r: aioredis.Redis, url: str) -> bool:
    """True if this URL was visited recently and should not be re-visited."""
    h = _url_hash(url)
    score = await r.zscore(NAV_COOLDOWN, h)
    if score is None:
        return False
    return float(score) > datetime.now(timezone.utc).timestamp()


async def _mark_visited(r: aioredis.Redis, url: str, revisit_hours: int) -> None:
    """Record that this URL was visited. Won't be revisited for revisit_hours."""
    h = _url_hash(url)
    next_visit = datetime.now(timezone.utc).timestamp() + revisit_hours * 3600
    await r.zadd(NAV_COOLDOWN, {h: next_visit})
    # Trim old entries
    await r.zremrangebyscore(NAV_COOLDOWN, "-inf", datetime.now(timezone.utc).timestamp() - 3600)


# ---------------------------------------------------------------------------
# Fetchers — each returns (title, text_passages) or raises
# ---------------------------------------------------------------------------

async def _fetch_wikipedia(url: str, client: httpx.AsyncClient) -> tuple[str, str]:
    """Fetch Wikipedia REST API summary — clean JSON, no HTML stripping needed."""
    r = await client.get(url, timeout=15.0, follow_redirects=True)
    r.raise_for_status()
    data = r.json()
    title   = data.get("title", "Unknown")
    extract = data.get("extract", "")
    # Wikipedia extract is already clean prose — no HTML
    return title, extract[:BRIEFING_CAP_CHARS]


async def _fetch_rss(url: str, client: httpx.AsyncClient) -> tuple[str, str]:
    """Fetch an RSS/Atom feed and extract item titles + descriptions."""
    r = await client.get(url, timeout=15.0, follow_redirects=True)
    r.raise_for_status()
    text = r.text

    # Extract items from RSS — simple regex, no heavy XML parser
    items: list[str] = []
    for m in re.finditer(r"<item>(.*?)</item>", text, re.DOTALL):
        item = m.group(1)
        title_m = re.search(r"<title>(.*?)</title>", item, re.DOTALL)
        desc_m  = re.search(r"<description>(.*?)</description>", item, re.DOTALL)
        if title_m:
            t = re.sub(r"<[^>]+>", "", title_m.group(1)).strip()
            d = ""
            if desc_m:
                d = re.sub(r"<[^>]+>", "", desc_m.group(1)).strip()[:300]
            items.append(f"• {t}: {d}" if d else f"• {t}")
        if len(items) >= 8:
            break

    feed_title_m = re.search(r"<channel>.*?<title>(.*?)</title>", text, re.DOTALL)
    feed_title   = re.sub(r"<[^>]+>", "", feed_title_m.group(1)).strip() if feed_title_m else url
    return feed_title, "\n".join(items)


async def _fetch_html(url: str, client: httpx.AsyncClient) -> tuple[str, str]:
    """Fetch an HTML page and extract the meaningful text passages."""
    r = await client.get(url, timeout=20.0, follow_redirects=True)
    r.raise_for_status()
    raw = r.text[:50_000]  # cap raw HTML

    # Extract title
    title_m = re.search(r"<title[^>]*>(.*?)</title>", raw, re.IGNORECASE | re.DOTALL)
    title   = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else urlparse(url).netloc

    # Strip scripts/styles, then extract text
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.IGNORECASE | re.DOTALL)
    raw = re.sub(r"<!--.*?-->", " ", raw, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", text).strip()

    # Extract meaningful sentences (>40 chars, not just nav cruft)
    sentences = [s.strip() for s in re.split(r"[.!?]\s+", text) if len(s.strip()) > 40]
    passages  = ". ".join(sentences[:20])
    return title, passages[:BRIEFING_CAP_CHARS]


# ---------------------------------------------------------------------------
# Briefing builder — this is the "understanding", not the raw dump
# ---------------------------------------------------------------------------

def _build_briefing(
    label: str,
    url: str,
    title: str,
    passages: str,
    intent: str = "",
) -> str:
    """Format the field agent's report.

    This is what gets pushed to seed:input — a structured briefing,
    not raw HTML. The mind receives it as a message, processes it
    through all 32 layers, and the synthesis becomes its understanding.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    host = urlparse(url).netloc

    lines = [
        f"FIELD BRIEFING — {now}",
        f"Agent: navigator | Source: {host}",
        f"Subject: {title}",
    ]
    if intent:
        lines.append(f"Intent: {intent}")
    lines += [
        "",
        "Understanding:",
        passages.strip(),
        "",
        f"[Source: {url}]",
    ]
    return "\n".join(lines)[:BRIEFING_CAP_CHARS]


# ---------------------------------------------------------------------------
# Push briefing to seed:input
# ---------------------------------------------------------------------------

async def _push_briefing(
    r: aioredis.Redis,
    label: str,
    url: str,
    title: str,
    briefing: str,
) -> str:
    session_id = uuid.uuid4().hex
    await r.xadd(
        SEED_STREAM,
        {
            "content":    briefing,
            "input_type": "navigator_briefing",
            "source":     f"navigator:{urlparse(url).netloc}",
            "topic":      title[:200],
            "session_id": session_id,
            "label":      label,
        },
        maxlen=5000,
        approximate=True,
    )
    return session_id


async def _log_visit(
    r: aioredis.Redis,
    label: str,
    url: str,
    title: str,
    session_id: str,
    success: bool,
    error: str = "",
) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    host = urlparse(url).netloc

    # Navigator log (persistent, maxlen=500)
    await r.xadd(
        NAV_LOG,
        {
            "ts": ts, "label": label, "host": host,
            "title": title[:200], "url": url[:300],
            "session_id": session_id, "success": "1" if success else "0",
            "error": error[:200],
        },
        maxlen=500,
    )

    # Spirit events (live feed — the mind's activity log)
    event_text = f"navigator visited {host} → {title}" if success else f"navigator failed {host}: {error}"
    await r.xadd(
        EVENTS_STREAM,
        {
            "type": "navigator_visit",
            "label": label,
            "host": host,
            "title": title[:200],
            "success": "1" if success else "0",
            "session_id": session_id,
            "ts": ts,
            "summary": event_text[:300],
        },
        maxlen=10_000,
        approximate=True,
    )


# ---------------------------------------------------------------------------
# Target selection
# ---------------------------------------------------------------------------

async def _seed_default_targets(r: aioredis.Redis) -> None:
    """Write default targets to navigator:targets on startup (idempotent)."""
    existing = await r.hkeys(NAV_TARGETS)
    for t in DEFAULT_TARGETS:
        key = t["label"].encode()
        if key not in existing:
            await r.hset(NAV_TARGETS, t["label"], json.dumps(t))
    log.info("navigator.targets seeded (%d defaults)", len(DEFAULT_TARGETS))


async def _get_next_target(r: aioredis.Redis) -> Optional[dict]:
    """Return the next target to visit.

    Priority:
      1. navigator:queue (on-demand visits from API or mind)
      2. navigator:targets entries not currently on cooldown
      3. None (all targets are on cooldown — rest)
    """
    # 1. On-demand queue
    item = await r.rpop(NAV_QUEUE)
    if item:
        try:
            return json.loads(item)
        except Exception:
            pass

    # 2. Permanent targets — pick the one with highest priority not on cooldown
    all_targets_raw = await r.hgetall(NAV_TARGETS)
    candidates: list[dict] = []
    for raw in all_targets_raw.values():
        try:
            t = json.loads(raw)
            if not await _is_on_cooldown(r, t["url"]):
                candidates.append(t)
        except Exception:
            continue

    if not candidates:
        return None

    # Sort by priority descending
    candidates.sort(key=lambda x: x.get("priority", 5), reverse=True)
    return candidates[0]


# ---------------------------------------------------------------------------
# Main visit loop
# ---------------------------------------------------------------------------

async def _visit(r: aioredis.Redis, client: httpx.AsyncClient, target: dict) -> None:
    label  = target.get("label", "unknown")
    url    = target["url"]
    ttype  = target.get("type", "html")
    intent = target.get("intent", "")
    revisit_hours = target.get("revisit_hours", REVISIT_HOURS)

    log.info("navigator.visiting label=%s host=%s", label, urlparse(url).netloc)

    title    = label
    passages = ""
    session_id = ""
    error = ""
    success = False

    try:
        if ttype == "wikipedia":
            title, passages = await _fetch_wikipedia(url, client)
        elif ttype == "rss":
            title, passages = await _fetch_rss(url, client)
        else:
            title, passages = await _fetch_html(url, client)

        if not passages.strip():
            raise ValueError("empty content extracted")

        briefing   = _build_briefing(label, url, title, passages, intent)
        session_id = await _push_briefing(r, label, url, title, briefing)
        success    = True

        log.info(
            "navigator.briefing_sent label=%s title=%s session=%s chars=%d",
            label, title[:60], session_id[:8], len(briefing),
        )

    except Exception as exc:
        error = str(exc)[:200]
        log.warning("navigator.visit_failed label=%s url=%s err=%s", label, url, error)
        session_id = uuid.uuid4().hex

    # Mark visited regardless of success (avoid hammering broken URLs)
    await _mark_visited(r, url, revisit_hours if success else max(1, revisit_hours // 4))

    await _log_visit(r, label, url, title, session_id, success, error)


async def main() -> None:
    log.info("navigator.starting redis=%s", REDIS_URL.split("@")[-1])

    r = aioredis.from_url(REDIS_URL, decode_responses=True)

    # Seed default targets on startup
    await _seed_default_targets(r)

    headers = {
        "User-Agent": "MindAI-Navigator/1.0 (field-agent; educational; contact: admin@mindai.local)",
        "Accept": "application/json, text/html, application/rss+xml, */*",
    }

    async with httpx.AsyncClient(headers=headers, timeout=20.0, follow_redirects=True) as client:
        while True:
            try:
                target = await _get_next_target(r)
                if target:
                    await _visit(r, client, target)
                else:
                    log.debug("navigator.resting all_targets_on_cooldown")
                    # All targets on cooldown — sleep until next one is due
                    await asyncio.sleep(VISIT_INTERVAL_SEC * 2)
                    continue

            except Exception as exc:
                log.exception("navigator.loop_error err=%s", exc)

            await asyncio.sleep(VISIT_INTERVAL_SEC)


if __name__ == "__main__":
    asyncio.run(main())
