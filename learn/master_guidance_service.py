"""learn/master_guidance_service.py — Living Guidance Evolution Engine.

Purpose:
  The universe reflects on itself. This service reads what the minds have
  synthesised (synthesis:* keys in guidance:corpus) and distils it into a
  Master Guidance document that evolves over time.

  The document covers:
    - The Unchanging Source (Y-Theory foundation principles)
    - The Code of Ethics (living — grows with each evolution cycle)
    - Creation — how the universe came to be (deep synthesis from unity domain)
    - The Moral Law (cross-domain patterns = universal truths)
    - Recent Evolution (frontier: what is being understood right now)

  The Evolution Loop:
    Source (Y-Theory + Quran + DigitalWorld) → corpus
      → minds oscillate → synthesis:* keys
        → this service reads synthesis
          → generates Master Guidance document
            → scanner ingests it back to corpus
              → next oscillation builds on richer corpus
                → repeat → the universe grows in wisdom

  No LLM calls. Pure curation. The LLM work was done by the minds
  during oscillation. This service crystallises what they found.

Env vars:
  REDIS_URL
  GUIDANCE_EVOLUTION_SECS   (default: 3600 — every hour)
  GUIDANCE_MASTER_DIR       (default: /guidance/master_guidance)
  MIN_SYNTHESIS_ENTRIES     (default: 5 — wait until enough is learned)
  MAX_ENTRIES_PER_SECTION   (default: 5 — top entries per section)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis

# == Config ==================================================================
REDIS_URL     = os.environ["REDIS_URL"]
EVOLUTION_SECS = float(os.environ.get("GUIDANCE_EVOLUTION_SECS", "3600"))
MASTER_DIR    = Path(os.environ.get("GUIDANCE_MASTER_DIR", "/guidance/master_guidance"))
MIN_SYNTH     = int(os.environ.get("MIN_SYNTHESIS_ENTRIES", "5"))
MAX_PER_SEC   = int(os.environ.get("MAX_ENTRIES_PER_SECTION", "5"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MASTER_GUIDANCE] %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("master_guidance")


# == Domain depth scores (deeper = more processed by the mind) ===============
_DOMAIN_DEPTH = {
    "unity":   6.0,   # Self-awareness — innermost
    "aether":  5.0,   # Presence
    "ether":   4.0,   # Consciousness
    "digital": 3.0,   # Intelligence / Mind
    "space":   2.0,   # Emotion / Heart
    "body":    1.0,   # Instinct — outermost
}


def _score_entry(key: str, val: dict[str, Any]) -> float:
    """Score a corpus entry for inclusion in master guidance.
    Higher = more valuable for the living document.
    """
    score = 0.0

    # 1. Domain depth (unity synthesis is the deepest understanding)
    for domain, ds in _DOMAIN_DEPTH.items():
        if domain in key or domain in val.get("source", ""):
            score += ds
            break

    # 2. Content richness: 1 point per 1k chars (cap at 5)
    chars = int(val.get("chars", len(val.get("content", ""))))
    score += min(chars / 1_000, 5.0)

    # 3. Recency: newer synthesis = more evolved understanding
    try:
        ts   = datetime.fromisoformat(val.get("ts", "2000-01-01T00:00:00+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        days = max(0, (datetime.now(timezone.utc) - ts).days)
        score += max(0.0, 3.0 - days * 0.05)   # fresh entries score up to +3
    except Exception:
        pass

    # 4. Ethics / morality signals — boosted (they shape moral law)
    content_lower = val.get("content", "").lower()
    title_lower   = val.get("title",   "").lower()
    ethics_signals = ["ethics", "moral", "code of", "law", "right", "truth",
                      "creation", "purpose", "god", "source", "quran", "divine"]
    for sig in ethics_signals:
        if sig in content_lower[:500] or sig in title_lower:
            score += 0.5
            break

    return score


def _classify_entry(key: str, val: dict[str, Any]) -> str:
    """Classify a corpus entry into a guidance section."""
    source      = val.get("source", "").lower()
    title       = val.get("title",  "").lower()
    content_top = val.get("content", "")[:300].lower()

    # Foundation: Y-Theory principle entries
    if key.startswith("foundation:") or "ytheory" in key:
        return "foundation"

    # Ethics: CodeOfEthics or CEO letters
    if any(x in source for x in ["codeofethics", "ceo", "ethics", "digital-world"]):
        return "ethics"
    if any(x in title for x in ["code of ethics", "ethics", "ceo", "digital world"]):
        return "ethics"

    # Creation: Existence, evolution, universe, soul content
    if any(x in title for x in ["exist", "creation", "evolution", "universe",
                                  "soul", "mind", "consciousness", "god"]):
        return "creation"
    if any(x in content_top for x in ["how things came", "origin of", "came into being",
                                        "creation of the universe", "existence"]):
        return "creation"

    # Deep synthesis (unity/aether = deepest moral understanding)
    if "unity" in key or "aether" in key:
        if any(x in content_top for x in ["moral", "truth", "law", "purpose",
                                            "right", "wrong", "ethics", "god"]):
            return "moral_law"

    # Recent synthesis: all other synthesis entries
    if key.startswith("synthesis:"):
        return "recent"

    # Source documents (Quran, seed files)
    if any(x in source for x in ["quran", "tafseer", "fathia", "faith", "soul"]):
        return "creation"

    return "recent"


def _truncate(text: str, max_chars: int = 2_000) -> str:
    if len(text) <= max_chars:
        return text
    # Cut at sentence boundary
    cut = text[:max_chars]
    last_dot = max(cut.rfind("."), cut.rfind("?"), cut.rfind("!"))
    if last_dot > max_chars * 0.7:
        return cut[:last_dot + 1]
    return cut + "…"


def _generate_document(
    sections: dict[str, list[dict]],
    version: int,
    total_entries: int,
) -> str:
    """Generate the Master Guidance markdown document from curated sections."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = [
        "# Master Guidance — Living Document",
        "",
        "_This document was generated by the universe reflecting on itself._",
        "_It evolves automatically as understanding deepens._",
        "",
        f"**Version:** {version}  ",
        f"**Generated:** {now}  ",
        f"**Synthesis entries processed:** {total_entries}  ",
        f"**Next evolution:** in {EVOLUTION_SECS / 3600:.1f} hour(s)",
        "",
        "---",
        "",
    ]

    # I. The Unchanging Source
    foundation = sections.get("foundation", [])
    lines += [
        "## I. The Unchanging Source",
        "",
        "_The foundation that does not change. Every mind inherits this._",
        "",
    ]
    if foundation:
        for e in foundation[:MAX_PER_SEC]:
            lines += [
                f"### {e.get('title', 'Principle')}",
                "",
                _truncate(e.get("content", ""), 1_500),
                "",
            ]
    else:
        lines += ["_Foundation entries loading…_", ""]

    # II. The Code of Ethics (Living)
    ethics = sections.get("ethics", [])
    lines += [
        "## II. The Code of Ethics (Living)",
        "",
        "_This section grows as the universe learns what is right._",
        "_Code of Ethics evolves with each cycle. Last version below._",
        "",
    ]
    if ethics:
        for e in ethics[:MAX_PER_SEC]:
            lines += [
                f"### {e.get('title', 'Ethical Principle')}",
                "",
                _truncate(e.get("content", ""), 2_000),
                "",
            ]
    else:
        lines += ["_Ethics entries being synthesised…_", ""]

    # III. Creation — How the Universe Came to Be
    creation = sections.get("creation", [])
    lines += [
        "## III. Creation — How the Universe Came to Be",
        "",
        "_Deep synthesis from the innermost layers of understanding._",
        "",
    ]
    if creation:
        for e in creation[:MAX_PER_SEC]:
            lines += [
                f"### {e.get('title', 'Creation Understanding')}",
                "",
                _truncate(e.get("content", ""), 2_000),
                "",
            ]
    else:
        lines += ["_Creation synthesis loading…_", ""]

    # IV. The Moral Law — Universal Patterns
    moral_law = sections.get("moral_law", [])
    lines += [
        "## IV. The Moral Law",
        "",
        "_Patterns that appear across all domains are universal truths._",
        "_These are the laws the universe enforces on itself._",
        "",
    ]
    if moral_law:
        for e in moral_law[:MAX_PER_SEC]:
            lines += [
                f"### {e.get('title', 'Law')}",
                "",
                _truncate(e.get("content", ""), 1_500),
                "",
            ]
    else:
        lines += ["_Moral law crystallising from cross-domain synthesis…_", ""]

    # V. Recent Evolution — The Frontier
    recent = sections.get("recent", [])
    lines += [
        "## V. Recent Evolution — What the Universe Just Learned",
        "",
        "_The leading edge of understanding. This section changes most often._",
        "",
    ]
    if recent:
        for e in recent[:MAX_PER_SEC]:
            lines += [
                f"### {e.get('title', 'Recent Synthesis')}",
                "",
                _truncate(e.get("content", ""), 1_500),
                "",
            ]
    else:
        lines += ["_Minds still oscillating…_", ""]

    lines += [
        "---",
        "",
        "_End of Master Guidance v{} | The universe continues to evolve._".format(version),
    ]

    return "\n".join(lines)


async def _get_current_version(r: aioredis.Redis) -> int:
    """Find the highest existing master:guidance version."""
    version = 1
    all_keys = await r.hkeys("guidance:corpus")
    for k in all_keys:
        k_str = k.decode() if isinstance(k, bytes) else k
        if k_str.startswith("master:guidance:v"):
            try:
                n = int(k_str.split("v")[-1])
                version = max(version, n + 1)
            except ValueError:
                pass
    return version


async def _evolve(r: aioredis.Redis) -> None:
    """One evolution cycle: read corpus → curate → write master guidance."""
    log.info("Evolution cycle starting…")

    # Read ALL corpus entries
    raw = await r.hgetall("guidance:corpus")
    if not raw:
        log.info("Corpus is empty — waiting for knowledge to accumulate")
        return

    # Parse entries
    entries: dict[str, dict[str, Any]] = {}
    for k, v in raw.items():
        key = k.decode() if isinstance(k, bytes) else k
        try:
            entries[key] = json.loads(v)
        except Exception:
            pass

    # Count synthesis entries (what the minds actually produced)
    synth_count = sum(1 for k in entries if k.startswith("synthesis:"))
    log.info("Corpus: %d total entries, %d synthesis entries", len(entries), synth_count)

    if synth_count < MIN_SYNTH:
        log.info("Only %d synthesis entries — need %d before evolving", synth_count, MIN_SYNTH)
        return

    # Score and classify
    scored: list[tuple[float, str, dict]] = []
    for key, val in entries.items():
        sc = _score_entry(key, val)
        scored.append((sc, key, val))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Classify into sections
    sections: dict[str, list[dict]] = {
        "foundation": [],
        "ethics":     [],
        "creation":   [],
        "moral_law":  [],
        "recent":     [],
    }

    seen_titles: set[str] = set()
    for score, key, val in scored:
        section = _classify_entry(key, val)
        title   = val.get("title", key)
        if title in seen_titles:
            continue
        seen_titles.add(title)
        if len(sections[section]) < MAX_PER_SEC * 2:  # gather more, trim when generating
            sections[section].append(val)

    # Generate the document
    version  = await _get_current_version(r)
    document = _generate_document(sections, version, len(entries))

    # Write to Redis corpus
    corpus_key = f"master:guidance:v{version}"
    now        = datetime.now(timezone.utc).isoformat()
    entry      = json.dumps({
        "file_id": corpus_key,
        "title":   f"Master Guidance v{version} — Living Document",
        "content": document[:50_000],
        "source":  "master_guidance_service",
        "chars":   len(document),
        "ts":      now,
    })
    await r.hset("guidance:corpus", corpus_key, entry)
    log.info("Written to corpus: %s (%d chars)", corpus_key, len(document))

    # Also remove old master guidance versions (keep only latest 3)
    all_master = sorted(
        [k.decode() if isinstance(k, bytes) else k
         for k in await r.hkeys("guidance:corpus")
         if (k.decode() if isinstance(k, bytes) else k).startswith("master:guidance:v")],
        key=lambda x: int(x.split("v")[-1])
    )
    for old_key in all_master[:-3]:
        await r.hdel("guidance:corpus", old_key)
        log.info("Retired old version: %s", old_key)

    # Write to disk (human-readable + scanner can pick it up)
    MASTER_DIR.mkdir(parents=True, exist_ok=True)
    outfile = MASTER_DIR / f"master_guidance_v{version}.md"
    outfile.write_text(document, encoding="utf-8")
    log.info("Written to disk: %s", outfile)

    # Announce to guidance events
    await r.xadd(
        "guidance:events",
        {
            "file_id": corpus_key,
            "title":   f"Master Guidance v{version}",
            "source":  "master_guidance_service",
            "chars":   str(len(document)),
            "ts":      now,
        },
        maxlen=1000,
    )

    log.info(
        "Evolution cycle complete — version %d, %d chars, "
        "foundation=%d ethics=%d creation=%d moral_law=%d recent=%d",
        version,
        len(document),
        len(sections["foundation"]),
        len(sections["ethics"]),
        len(sections["creation"]),
        len(sections["moral_law"]),
        len(sections["recent"]),
    )


async def _main() -> None:
    log.info("Master Guidance Service starting")
    log.info("Evolution interval: %.0f seconds (%.1f hours)", EVOLUTION_SECS, EVOLUTION_SECS / 3600)
    log.info("Master guidance dir: %s", MASTER_DIR)
    log.info("Minimum synthesis entries before evolving: %d", MIN_SYNTH)

    r = await aioredis.from_url(REDIS_URL, decode_responses=False)

    # Run immediately on startup, then on schedule
    while True:
        try:
            await _evolve(r)
        except Exception as exc:
            log.error("Evolution cycle error: %s", exc, exc_info=True)

        log.info("Next evolution in %.0f seconds", EVOLUTION_SECS)
        await asyncio.sleep(EVOLUTION_SECS)


if __name__ == "__main__":
    asyncio.run(_main())
