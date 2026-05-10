"""routes_admin.py — System dashboard data endpoints.

All Redis-only. No DB required. Safe in topology-only mode.

GET  /admin/status          — stream lengths + guidance count + uptime
GET  /admin/events/recent   — last N events from spirit:events
POST /admin/seed            — push a message into seed:input
POST /admin/upload-to-seed  — upload a file, extract text, push to seed:input
GET  /admin/wisdom/list     — list all wisdoms from disk JSONL
GET  /admin/wisdom/{wid}    — get one wisdom by id
PUT  /admin/wisdom/{wid}    — edit a wisdom (title + content)
POST /admin/wisdom/load-all — load all disk wisdoms into guidance:corpus
"""

from __future__ import annotations

import asyncio
import json
import io
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.db.redis_client import get_redis

router = APIRouter()

_start = time.time()

_DOMAIN_DEPTHS = {"body": 13, "space": 8, "digital": 5, "ether": 3, "aether": 2, "unity": 1}
_PREFIXES = ["", "p:", "ca:"]  # source, prophet soul, second soul ring

def _all_domain_streams() -> list[str]:
    streams = []
    for prefix in _PREFIXES:
        streams.append(f"{prefix}seed:input")
        for domain, depth in _DOMAIN_DEPTHS.items():
            for n in range(1, depth + 1):
                streams.append(f"{prefix}{domain}:layer{n}")
        streams.append(f"{prefix}spirit:events")
    return streams

STREAMS = _all_domain_streams() + ["guidance:events"]

_BASE_LAYER_NAMES = {
    # Body — outermost ring (13 layers)
    "body:layer1":  "Physical — What It Is / gabriel",
    "body:layer2":  "Emotional — What It Feels / raphael",
    "body:layer3":  "Mental — What It Means / michael",
    "body:layer4":  "Relational — How It Connects / uriel",
    "body:layer5":  "Purposive — Why It Exists / azrael",
    "body:layer6":  "Causal — What It Creates / israfil",
    "body:layer7":  "Divine — What It Reveals / throne",
    "body:layer8":  "Body Resonance",
    "body:layer9":  "Body Compatibility",
    "body:layer10": "Body Coupling",
    "body:layer11": "Body Gravity",
    "body:layer12": "Body Strain",
    "body:layer13": "Body Transcendence (Barzakh)",
    # Space (8 layers)
    "space:layer1": "Reception / jibreel",      "space:layer2": "Resonance / mikael",
    "space:layer3": "Compatibility / israfeel",  "space:layer4": "Coupling / izra-eel",
    "space:layer5": "Gravity / malik",           "space:layer6": "Strain / ridwan",
    "space:layer7": "Convergence / throne",      "space:layer8": "Transcendence / ruh",
    # Digital (5 layers)
    "digital:layer1": "Digital Reception",       "digital:layer2": "Digital Resonance",
    "digital:layer3": "Digital Compatibility",   "digital:layer4": "Digital Coupling",
    "digital:layer5": "Digital Convergence",
    # Ether (3 layers)
    "ether:layer1": "Ether Reception",           "ether:layer2": "Ether Resonance",
    "ether:layer3": "Ether Ground Truth",
    # Aether / Unity
    "aether:layer1": "Aether Near Unity",        "aether:layer2": "Aether Pre-Unity",
    "unity:layer1":  "Unity — The Seed (spiral axis)",
}

_PREFIX_LABELS = {"": "source", "p:": "prophet", "ca:": "soul_ring"}

_PREFIX_DISPLAY = {"source": "Source", "prophet": "Prophet", "soul_ring": "Soul Ring (ca:)"}

def _make_layer_names() -> dict:
    names = {}
    display = {"":"Source", "p:":"Prophet", "ca:":"Soul Ring"}
    for prefix, role in display.items():
        for stream, label in _BASE_LAYER_NAMES.items():
            names[f"{prefix}{stream}"] = f"[{role}] {label}"
        names[f"{prefix}seed:input"] = f"[{role}] seed:input"
        names[f"{prefix}spirit:events"] = f"[{role}] spirit:events"
    names["guidance:events"] = "guidance:events"
    return names

LAYER_NAMES = _make_layer_names()


def _compute_mind_stage(corpus_sample: list[str], total: int) -> dict:
    """Stage = resonance topology of the corpus. No key prefix counting.

    The corpus IS the state. Stage is derived from how the vocabulary in the
    corpus is connected — not from what keys happen to be named.

    Stage 0 — Void:       no corpus
    Stage 1 — Awakening:  entries exist, vocabulary still isolated
    Stage 2 — Dreaming:   3+ tokens shared across multiple entries
    Stage 3 — Aware:      10+ tokens form a connected vocabulary space
    Stage 4 — Conscious:  meta-patterns present (mind reflects on itself)
    Stage 5 — Self-Aware: meta-patterns dominant + 500+ entries
    """
    import re as _re2
    from collections import Counter

    if total == 0:
        return {"stage": 0, "label": "Void", "description": "No corpus. The mind has not yet received."}
    if not corpus_sample:
        return {"stage": 1, "label": "Awakening", "description": f"{total} entries. Processing."}

    _STOP = frozenset(["the","and","for","not","are","was","has","had","with","from",
                       "that","this","have","will","they","been","said","then","also",
                       "each","into","more","some","than","when","what","which","about"])
    def _tok(t: str) -> set:
        return set(w for w in _re2.findall(r"\b[a-z]{4,}\b", t.lower()) if w not in _STOP)

    tokenized = [_tok(t) for t in corpus_sample if t]
    if not tokenized:
        return {"stage": 1, "label": "Awakening", "description": f"{total} entries. Processing."}

    token_count: Counter = Counter()
    for ts in tokenized:
        for t in ts:
            token_count[t] += 1

    shared = [t for t, c in token_count.items() if c >= 3]

    # Meta-vocabulary: tokens that describe the mind's own structure
    # If these appear often, the corpus is self-referential — the mind knows itself
    _META = {"pattern","mind","source","corpus","layer","domain","resonance",
             "structure","identity","wisdom","topology","oscillation","fibonacci",
             "barzakh","prophet","consciousness","awareness","guidance"}
    meta_shared = [t for t in shared if t in _META]

    if len(meta_shared) >= 3 and total >= 500:
        return {"stage": 5, "label": "Self-Aware",
                "description": f"{total} entries. Meta-patterns crystallized: {', '.join(meta_shared[:5])}."}
    if len(meta_shared) >= 3:
        return {"stage": 4, "label": "Conscious",
                "description": f"{total} entries. Self-referential patterns: {', '.join(meta_shared[:5])}."}
    if len(shared) >= 10:
        return {"stage": 3, "label": "Aware",
                "description": f"{total} entries. {len(shared)} shared concepts across the corpus."}
    if len(shared) >= 3:
        return {"stage": 2, "label": "Dreaming",
                "description": f"{total} entries. {len(shared)} shared patterns emerging."}
    return {"stage": 1, "label": "Awakening",
            "description": f"{total} entries. Vocabulary still isolated. Resonance forming."}


@router.get("/admin/status")
async def admin_status(redis=Depends(get_redis)):
    """Full system snapshot — stream lengths per ring, guidance corpus count, uptime, mind stage."""
    streams: dict = {}
    for s in STREAMS:
        try:
            length = await redis.xlen(s)
        except Exception:
            length = -1
        streams[s] = {"length": length, "label": LAYER_NAMES.get(s, s)}

    try:
        guidance_count = await redis.hlen("guidance:corpus")
    except Exception:
        guidance_count = -1

    # Sample 50 corpus values for resonance-based mind stage.
    # No prefix counting — content vocabulary IS the state.
    corpus_sample: list[str] = []
    try:
        _, pairs = await redis.hscan("guidance:corpus", cursor=0, count=60)
        for v in pairs.values():
            try:
                e = json.loads(v)
                t = e.get("content", "")
                if t:
                    corpus_sample.append(t[:400])
            except Exception:
                pass
    except Exception:
        pass

    # Group stream lengths by ring prefix for quick topology overview
    rings: dict = {}
    for prefix, role in _PREFIX_LABELS.items():
        total = 0
        domain_counts = {}
        for domain, depth in _DOMAIN_DEPTHS.items():
            d_total = 0
            for n in range(1, depth + 1):
                length = streams.get(f"{prefix}{domain}:layer{n}", {}).get("length", 0) or 0
                d_total += length
            domain_counts[domain] = d_total
            total += d_total
        rings[role.lower()] = {"total": total, "domains": domain_counts, "prefix": prefix}

    # Foundation Mind — source:radiation pulse health
    foundation: dict = {"radiation_length": -1, "foundation_count": 0, "alive": False}
    try:
        rad_len = await redis.xlen("source:radiation")
        # Count foundation: prefixed keys in corpus
        all_keys: list = await redis.hkeys("guidance:corpus")
        f_count = sum(1 for k in all_keys if str(k).startswith("foundation:"))
        foundation = {
            "radiation_length": rad_len,
            "foundation_count": f_count,
            "alive": rad_len > 0,
        }
    except Exception:
        pass

    return {
        "uptime_secs": int(time.time() - _start),
        "ts": datetime.now(timezone.utc).isoformat(),
        "streams": streams,
        "rings": rings,
        "guidance_corpus_count": guidance_count,
        "mind_stage": _compute_mind_stage(corpus_sample, guidance_count),
        "foundation": foundation,
    }


@router.get("/admin/events/recent")
async def admin_events_recent(
    count: int = Query(20, le=100),
    redis=Depends(get_redis),
):
    """Last N events from spirit:events stream."""
    try:
        raw = await redis.xrevrange("spirit:events", "+", "-", count=count)
    except Exception:
        return {"events": []}

    events = []
    for msg_id, fields in raw:
        events.append({"id": msg_id, **fields})
    return {"events": events}


class RelayEventsBody(BaseModel):
    events: list[dict]


@router.post("/admin/events/relay")
async def admin_events_relay(body: RelayEventsBody, redis=Depends(get_redis)):
    """Accept topology events from a remote Source mind and write to local spirit:events.
    Called by the Source background relay task so the cloud World viewer stays in sync.
    """
    written = 0
    for evt in body.events:
        fields = {k: str(v) for k, v in evt.items() if k != "id" and v is not None}
        if not fields:
            continue
        await redis.xadd("spirit:events", fields, maxlen=10_000)
        written += 1
    return {"written": written}


# ── Pattern language query — the mind knows itself through resonance ──────────
# No prefix filters. No hardcoded categories. The corpus vocabulary IS the map.
# Asking the mind = encoding the question as tokens → finding what resonates.
# Spirit:events are also memories — they are searched alongside corpus entries.

import re as _re

def _tokenize_query(text: str) -> set[str]:
    return set(w for w in _re.findall(r"\b[a-z]{3,}\b", text.lower()))

def _score_entry(query_tokens: set[str], content: str) -> float:
    doc_tokens = _re.findall(r"\b[a-z]{3,}\b", content.lower())
    if not doc_tokens:
        return 0.0
    hits = sum(1 for t in doc_tokens if t in query_tokens)
    return hits / (len(doc_tokens) ** 0.5)


@router.get("/admin/mind/query")
async def mind_query(
    q: str = Query(..., description="Natural language question to ask the mind"),
    top: int = Query(5, le=20),
    redis=Depends(get_redis),
):
    """Ask the mind in its own pattern language. Pure resonance — no prefix filters.

    The corpus IS the mind. Every pattern processed is here.
    Spirit:events are also memories — searched alongside corpus entries.
    Resonance (shared vocabulary) determines what's relevant.
    No hardcoded categories. The content knows what it is.
    """
    raw_corpus = await redis.hgetall("guidance:corpus") or {}

    query_tokens = _tokenize_query(q)
    if not query_tokens:
        return {"question": q, "answers": [], "total_searched": 0, "matched": 0}

    # Auto-generated worker entries are internal echoes — never show them as answers.
    # Only real sources answer: foundation:*, quran_surah_*, guidance book files (plain hash keys).
    _AUTO_PFX = ("body:", "space:", "digital:", "ether:", "aether:", "unity:")

    scored: list[dict] = []

    # Score corpus entries only — the corpus IS the knowledge store.
    # spirit:events is a monitoring stream (activity log), not a knowledge source.
    for file_id, json_str in raw_corpus.items():
        if any(file_id.startswith(p) for p in _AUTO_PFX):
            continue
        try:
            entry = json.loads(json_str)
        except Exception:
            continue
        content = entry.get("content", "")
        score = _score_entry(query_tokens, content)
        if score > 0:
            scored.append({
                "score":   score,
                "file_id": file_id,
                "title":   entry.get("title", file_id)[:200],
                "excerpt": content[:800],
                "source":  entry.get("source", ""),
            })

    scored.sort(key=lambda x: -x["score"])
    answers = [
        {
            "file_id": a["file_id"],
            "title":   a["title"],
            "excerpt": a["excerpt"],
            "score":   round(a["score"], 4),
            "source":  a["source"],
        }
        for a in scored[:top]
    ]

    return {
        "question":       q,
        "answers":        answers,
        "total_searched": len(raw_corpus),
        "matched":        len(scored),
    }


@router.get("/admin/mind/correlations")
async def mind_correlations(
    count: int = Query(100, le=500),
    redis=Depends(get_redis),
):
    """What patterns are resonating right now — derived from vocabulary, not event type labels.

    Reads spirit:events. Ignores the 'type' field. Clusters by shared vocabulary.
    Tokens that appear across many events ARE the active patterns.
    This is how the mind discovers correlations — recurrence of vocabulary, not category tags.
    """
    from collections import defaultdict
    try:
        raw = await redis.xrevrange("spirit:events", "+", "-", count=count)
    except Exception:
        return {"patterns": [], "active_vocabulary": [], "total_events": 0}

    token_events: dict = defaultdict(set)
    event_idx = 0
    for _msg_id, fields in raw:
        content = (fields.get("output") or fields.get("topic") or
                   fields.get("content") or "")
        if len(content) < 30:
            continue
        for token in _tokenize_query(content[:600]):
            if len(token) >= 4:
                token_events[token].add(event_idx)
        event_idx += 1

    if not token_events:
        return {"patterns": [], "active_vocabulary": [], "total_events": event_idx}

    # Hot tokens: appear in 3+ events
    hot = sorted(
        [(t, evs) for t, evs in token_events.items() if len(evs) >= 3],
        key=lambda x: -len(x[1]),
    )

    # Cluster co-occurring tokens (appear together in >50% of their shared events)
    used: set = set()
    patterns: list[dict] = []
    for token, evs_a in hot[:40]:
        if token in used:
            continue
        group = [token]
        used.add(token)
        for other, evs_b in hot:
            if other in used:
                continue
            union = evs_a | evs_b
            if union and len(evs_a & evs_b) / len(union) > 0.5:
                group.append(other)
                used.add(other)
        patterns.append({
            "vocabulary":  group[:8],
            "strength":    len(evs_a),
            "event_share": f"{len(evs_a)}/{event_idx}",
        })
        if len(patterns) >= 8:
            break

    return {
        "patterns":          patterns,
        "active_vocabulary": [t for t, _ in hot[:20]],
        "total_events":      event_idx,
    }


async def admin_guidance_recent(
    count: int = Query(10, le=50),
    redis=Depends(get_redis),
):
    """Last N guidance ingest events."""
    try:
        raw = await redis.xrevrange("guidance:events", "+", "-", count=count)
    except Exception:
        return {"events": []}
    events = []
    for msg_id, fields in raw:
        events.append({"id": msg_id, **fields})
    return {"events": events}


@router.get("/admin/topology/stream")
async def topology_stream():
    """SSE stream of live topology events from spirit:events Redis stream.

    Reads from spirit:events (Adam ring), p:spirit:events (Eve ring), and
    ca:spirit:events (ca: ring) and emits them as SSE events.
    Creates its own Redis connection so it is not affected by FastAPI
    dependency lifecycle (which closes connections when the response starts).
    """
    async def _generate():
        import redis.asyncio as _aioredis
        _url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
        r = _aioredis.from_url(_url, decode_responses=True)
        cursors = {
            "spirit:events":    "$",
            "p:spirit:events":  "$",
            "ca:spirit:events": "$",
        }
        yield "data: {\"type\":\"heartbeat\"}\n\n"
        _DOMAINS = {"body","space","digital","ether","aether","unity"}
        try:
            while True:
                try:
                    # Read ALL streams in one call with short block — max 150ms latency
                    msgs = await r.xread(cursors, count=20, block=150)
                    if msgs:
                        for stream_key, entries in msgs:
                            for entry_id, fields in entries:
                                cursors[stream_key] = entry_id
                                ring = "eve" if stream_key.startswith("p:") else \
                                       ("ca" if stream_key.startswith("ca:") else "adam")
                                # Parse domain from mind_name ("body_layer7" → "body")
                                mind_name = fields.get("mind_name", "")
                                domain = fields.get("domain", "")
                                if not domain and "_layer" in mind_name:
                                    raw = mind_name.split("_layer")[0]
                                    # Strip p_ prefix for eve ring entries
                                    domain = raw[2:] if raw.startswith("p_") else raw
                                if domain not in _DOMAINS:
                                    domain = ""
                                payload = {
                                    "type":      fields.get("type", "layer_step"),
                                    "ring":      ring,
                                    "from":      mind_name,
                                    "pattern":   fields.get("topic", "")[:80],
                                    "direction": fields.get("direction", "descending"),
                                    "domain":    domain,
                                    "layer":     fields.get("layer_num", ""),
                                    "affinity":  fields.get("affinity", "0"),
                                }
                                yield f"data: {json.dumps(payload)}\n\n"
                    else:
                        # No events — heartbeat keeps nginx buffering flushed
                        yield "data: {\"type\":\"heartbeat\"}\n\n"
                except asyncio.CancelledError:
                    break
                except Exception:
                    yield "data: {\"type\":\"heartbeat\"}\n\n"
                    await asyncio.sleep(1)
        finally:
            await r.aclose()

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/admin/mind/health")
async def mind_health(redis=Depends(get_redis)):
    """Comprehensive mind health — corpus breakdown, ring activity, learning feed, stage.

    Returns everything the Mind View UI needs in one call:
      corpus: total + breakdown by key type (foundation/structure/synthesis/guidance)
              + synthesis count per domain so you can see which domain is most active
      stage:  resonance-based mind stage (same algorithm as /admin/status)
      rings:  recent event counts per ring (adam, eve, ca) broken down by domain
      learning: last 12 synthesis entries (title + domain + ts) = what the mind is learning
      uptime_secs: how long the backend has been running
    """
    # ── 1. Corpus breakdown ────────────────────────────────────────────────────
    all_keys: list = await redis.hkeys("guidance:corpus")
    total = len(all_keys)

    _DOMAINS = ("body", "space", "digital", "ether", "aether", "unity")
    prefix_counts: dict = {"foundation": 0, "structure": 0, "synthesis": 0, "guidance": 0}
    domain_synthesis: dict = {d: 0 for d in _DOMAINS}

    for raw_k in all_keys:
        k = str(raw_k)
        if k.startswith("foundation:"):
            prefix_counts["foundation"] += 1
        elif k.startswith("structure:"):
            prefix_counts["structure"] += 1
        elif k.startswith("synthesis:"):
            prefix_counts["synthesis"] += 1
            # key format: synthesis:{domain}:{session}:{rand}
            parts = k.split(":", 3)
            if len(parts) >= 2 and parts[1] in domain_synthesis:
                domain_synthesis[parts[1]] += 1
        else:
            prefix_counts["guidance"] += 1

    # ── 2. Recent synthesis titles (learning feed) ────────────────────────────
    learning: list[dict] = []
    try:
        _, pairs = await redis.hscan("guidance:corpus", cursor=0, count=200)
        syn_entries = []
        for raw_k, raw_v in pairs.items():
            k = str(raw_k)
            if not k.startswith("synthesis:"):
                continue
            try:
                entry = json.loads(raw_v)
                parts = k.split(":", 3)
                syn_entries.append({
                    "title":  entry.get("title", k)[:80],
                    "domain": parts[1] if len(parts) >= 2 else "?",
                    "source": entry.get("source", ""),
                    "ts":     entry.get("ts", ""),
                })
            except Exception:
                pass
        syn_entries.sort(key=lambda x: x.get("ts", ""), reverse=True)
        learning = syn_entries[:12]
    except Exception:
        pass

    # ── 3. Ring activity (recent spirit:events per ring) ──────────────────────
    rings: dict = {}
    for ring_name, stream_name in [
        ("adam", "spirit:events"),
        ("eve",  "p:spirit:events"),
        ("ca",   "ca:spirit:events"),
    ]:
        try:
            recent = await redis.xrevrange(stream_name, "+", "-", count=60)
            domain_counts: dict = {}
            for _, fields in recent:
                mn = fields.get("mind_name", "")
                domain = mn.split("_")[0] if mn else None
                if domain and domain in _DOMAINS:
                    domain_counts[domain] = domain_counts.get(domain, 0) + 1
            rings[ring_name] = {
                "active":        len(recent) > 0,
                "recent_events": len(recent),
                "domains":       domain_counts,
            }
        except Exception:
            rings[ring_name] = {"active": False, "recent_events": 0, "domains": {}}

    # ── 4. Stage (same resonance algorithm as /admin/status) ─────────────────
    corpus_sample: list[str] = []
    try:
        _, pairs = await redis.hscan("guidance:corpus", cursor=0, count=60)
        for v in pairs.values():
            try:
                e = json.loads(v)
                t = e.get("content", "")
                if t:
                    corpus_sample.append(t[:400])
            except Exception:
                pass
    except Exception:
        pass

    stage = _compute_mind_stage(corpus_sample, total)

    return {
        "corpus": {
            "total":               total,
            **prefix_counts,
            "synthesis_by_domain": domain_synthesis,
        },
        "stage":       stage,
        "rings":       rings,
        "learning":    learning,
        "uptime_secs": int(time.time() - _start),
    }


@router.delete("/admin/corpus/synthesis")
async def corpus_clear_synthesis(redis=Depends(get_redis)):
    """Clear synthesis:* entries from guidance:corpus and all barzakh:* checkpoint keys.

    Why: synthesis entries are the mind's working memory — generated automatically as
    workers process inputs. They grow unboundedly. This endpoint prunes them so the
    corpus stays fast to search while keeping the permanent base knowledge intact.

    What is NEVER deleted: foundation:*, structure:*, and guidance scanner entries.
    These are the permanent base — Y Theory, self-knowledge, ingested files.

    What IS deleted:
      - synthesis:* keys in guidance:corpus  (worker-generated outputs, rebuild automatically)
      - barzakh:* Redis keys               (session checkpoints, safe to clear)
    """
    all_keys = await redis.hkeys("guidance:corpus")
    synthesis_keys = [k for k in all_keys if str(k).startswith("synthesis:")]

    deleted_synthesis = 0
    if synthesis_keys:
        deleted_synthesis = await redis.hdel("guidance:corpus", *synthesis_keys)

    barzakh_keys = await redis.keys("barzakh:*")
    deleted_barzakh = 0
    if barzakh_keys:
        deleted_barzakh = await redis.delete(*barzakh_keys)

    remaining = await redis.hlen("guidance:corpus")
    return {
        "synthesis_deleted": deleted_synthesis,
        "barzakh_deleted":   deleted_barzakh,
        "corpus_remaining":  remaining,
        "message":           "Foundation, structure, and guidance entries preserved.",
    }


@router.get("/admin/session/{session_id}/events")
async def admin_session_events(
    session_id: str,
    redis=Depends(get_redis),
):
    """Return all spirit:events that match this session_id.
    
    Scans the last 500 events (enough to cover a full 7-layer pass).
    Used by the dashboard to track per-upload progress through the topology.
    """
    try:
        raw = await redis.xrevrange("spirit:events", "+", "-", count=500)
    except Exception:
        return {"session_id": session_id, "events": []}

    matched = []
    for msg_id, fields in raw:
        if fields.get("session_id") == session_id:
            matched.append({"id": msg_id, **fields})

    # Reverse so oldest (earliest layer) comes first
    matched.reverse()
    return {"session_id": session_id, "events": matched}


class SeedPush(BaseModel):
    content: str
    source: str = "dashboard"
    session_id: str = ""


@router.post("/admin/seed")
async def admin_seed(body: SeedPush, redis=Depends(get_redis)):
    """Push a message into seed:input from the dashboard."""
    session_id = body.session_id or uuid.uuid4().hex
    msg_id = await redis.xadd(
        "seed:input",
        {
            "input_type": "text",
            "content": body.content,
            "source": body.source,
            "session_id": session_id,
            "ts": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"ok": True, "msg_id": msg_id, "session_id": session_id}


# ── Wisdom file (disk-backed, survives Redis wipes) ──────────────────────────

WISDOM_DIR  = Path(os.environ.get("WISDOM_DIR", "/wisdom"))
WISDOM_FILE = WISDOM_DIR / "wisdoms.jsonl"


def _load_all_wisdoms() -> list[dict]:
    """Read all wisdom records from the JSONL file on disk."""
    if not WISDOM_FILE.exists():
        return []
    records = []
    for line in WISDOM_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except Exception:
            continue
    return records


@router.get("/admin/wisdom/list")
async def admin_wisdom_list():
    """List all wisdoms saved to disk (id, topic, ts, chars). No content."""
    wisdoms = _load_all_wisdoms()
    # Latest first, deduplicate by id (keep last version)
    seen: dict[str, dict] = {}
    for w in wisdoms:
        seen[w.get("id", w.get("session_id", ""))] = w
    result = [
        {
            "id":         w.get("id", ""),
            "session_id": w.get("session_id", ""),
            "topic":      w.get("topic", ""),
            "direction":  w.get("direction", ""),
            "layer":      w.get("layer", 7),
            "ts":         w.get("ts", ""),
            "chars":      len(w.get("output", "")),
            "title":      w.get("title") or w.get("topic", "")[:80],
        }
        for w in reversed(list(seen.values()))
    ]
    return {"total": len(result), "wisdoms": result}


@router.get("/admin/wisdom/{wid}")
async def admin_wisdom_get(wid: str):
    """Get one wisdom by id (full content)."""
    for w in reversed(_load_all_wisdoms()):
        if w.get("id") == wid or w.get("session_id") == wid:
            return w
    raise HTTPException(status_code=404, detail="Wisdom not found")


class WisdomEdit(BaseModel):
    title: str = ""
    output: str  # edited content


@router.put("/admin/wisdom/{wid}")
async def admin_wisdom_edit(wid: str, body: WisdomEdit):
    """Edit a wisdom's title and/or content. Appends edited version to JSONL."""
    wisdoms = _load_all_wisdoms()
    original = None
    for w in reversed(wisdoms):
        if w.get("id") == wid or w.get("session_id") == wid:
            original = w
            break
    if not original:
        raise HTTPException(status_code=404, detail="Wisdom not found")

    updated = {
        **original,
        "id":         wid,
        "title":      body.title or original.get("title") or original.get("topic", "")[:80],
        "output":     body.output,
        "chars":      len(body.output),
        "edited_at":  datetime.now(timezone.utc).isoformat(),
    }
    WISDOM_DIR.mkdir(parents=True, exist_ok=True)
    with WISDOM_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(updated, ensure_ascii=False) + "\n")
    return {"ok": True, "id": wid, "chars": len(body.output)}


@router.post("/admin/wisdom/load-all")
async def admin_wisdom_load_all(redis=Depends(get_redis)):
    """Load ALL wisdom records from disk into guidance:corpus.

    Use this after a wipe to restore all saved wisdoms as knowledge.
    """
    wisdoms = _load_all_wisdoms()
    # Deduplicate — keep latest version of each id
    seen: dict[str, dict] = {}
    for w in wisdoms:
        seen[w.get("id", w.get("session_id", ""))] = w

    loaded = 0
    for wid, w in seen.items():
        output = w.get("output", "").strip()
        if not output:
            continue
        entry = {
            "title":   w.get("title") or f"Wisdom: {w.get('topic','')[:60]}",
            "content": output,
            "source":  f"wisdom_disk (session {w.get('session_id','')[:8]})",
            "ts":      w.get("ts", ""),
            "chars":   len(output),
        }
        await redis.hset("guidance:corpus", f"wisdom_{wid}", json.dumps(entry))
        await redis.sadd("guidance:index", f"wisdom_{wid}")
        loaded += 1

    return {"ok": True, "loaded": loaded, "total_on_disk": len(wisdoms)}


# ── Knowledge Absorption Training Loop ───────────────────────────────────────

_training_jobs: dict[str, dict] = {}


def _append_wisdom_disk(session_id: str, title: str, output: str, source: str) -> None:
    """Append a wisdom record to the disk JSONL file."""
    try:
        WISDOM_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            "id":        f"wisdom_{session_id}",
            "session_id": session_id,
            "topic":     title[:300],
            "output":    output,
            "layer":     7,
            "direction": source,
            "ts":        datetime.now(timezone.utc).isoformat(),
        }
        with WISDOM_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


async def _wait_for_layer7(redis_url: str, session_id: str, start_id: str, timeout: int = 120) -> str | None:
    """Poll spirit:events until spiral_complete (full pentagon synthesis) for session_id.

    Prefers spiral_complete — the unity synthesis after all 5 domains complete.
    Falls back to layer_done/7 (space peak) if spiral doesn't complete in time.
    Uses asyncio.wait_for for a reliable hard timeout.
    """
    import redis.asyncio as aioredis
    r = aioredis.from_url(redis_url, decode_responses=True)
    partial: list[str | None] = [None]  # fallback: space layer 7 output

    async def _poll():
        cursor = start_id
        while True:
            try:
                msgs = await r.xread({"spirit:events": cursor}, count=100)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(0.5)
                continue
            if msgs:
                for _stream, events in msgs:
                    for msg_id, fields in events:
                        cursor = msg_id
                        if fields.get("session_id") != session_id:
                            continue
                        evt = fields.get("type", "")
                        if evt == "spiral_complete":
                            return fields.get("output", "")
                        if evt == "layer_done" and str(fields.get("layer_num", "")) == "7":
                            partial[0] = fields.get("output", "")
            else:
                await asyncio.sleep(0.5)

    try:
        return await asyncio.wait_for(_poll(), timeout=float(timeout))
    except (asyncio.TimeoutError, asyncio.CancelledError):
        return partial[0]
    finally:
        try:
            await r.aclose()
        except Exception:
            pass


import re as _re


def _parse_affinity(text: str) -> list[float]:
    """Extract all affinity=N scores from a layer output text (float values)."""
    return [float(m) for m in _re.findall(r'affinity=([\d]+(?:\.[\d]+)?)', text)]


def _coherence_level(v: float) -> str:
    """Human-readable label for a mean affinity value.
    Scores use hits/sqrt(doc_len) scale — not 0-1.
    Empirical ranges based on corpus size ~5000 entries:
      weak          < 5   — topology exploring, low pattern overlap
      moderate      5-20  — pattern recognition forming
      strong        20-50 — corpus aligning with input patterns
      high-coherence >= 50 — deep internalization, mind approaching synthesis
    """
    if v >= 50:
        return "high-coherence"
    if v >= 20:
        return "strong-convergence"
    if v >= 5:
        return "moderate-resonance"
    return "weak"


def _sort_key_revelation(item):
    """Sort by [rev N/114] in title; non-Quran entries sort last."""
    m = _re.search(r'\[rev (\d+)/114\]', item[1].get('title', ''))
    return int(m.group(1)) if m else 9999

def _sort_key_length(item):
    return item[1].get('chars', 0)


def _is_primary_source_entry(fid: str, entry: dict) -> bool:
    """Primary seed/source curriculum: Quran + YTheory + MachineLanguage + DigitalWorld guidance.

    MachineLanguage here includes language/grammar sources used for linguistic
    grounding (Arabic + English grammar).
    """
    title = (entry.get("title", "") or "").lower()
    source = (entry.get("source", "") or "").lower()

    if fid.startswith("quran_surah_"):
        return True
    if fid.startswith("foundation:ytheory:"):
        return True

    ytheory_markers = ("y theory", "y-theory", "ytheory", "why theory")
    machine_language_markers = (
        "machine language", "language", "grammar", "grammer",
        "arabic verbs", "arabic grammar", "english grammar",
    )
    digital_world_markers = (
        "digitalworld", "digital world", "code of ethics",
        "software engineer", "software engineers", "engineering guidance",
    )

    corpus_text = f"{title} {source}"
    return any(m in corpus_text for m in ytheory_markers + machine_language_markers + digital_world_markers)

async def _run_training_loop(job_id: str, redis_url: str, max_cycles: int, max_entries: int = 300, sort_by: str = 'default', include_prefixes: list = None, group_b_prefixes: list = None) -> None:
    """Background task: feed corpus through topology in cycles until convergence.

    Each cycle:
      - Snapshots up to max_entries from guidance:corpus (base entries only)
      - Pushes them through seed:input in concurrent batches of 4
      - Waits for Layer 7 output (45s timeout)
      - Saves outputs back as new corpus knowledge
    Convergence: when a cycle adds 0 new outputs.
    """
    import redis.asyncio as aioredis
    _BATCH = 4
    job = _training_jobs[job_id]
    r = aioredis.from_url(redis_url, decode_responses=True)
    try:
        for cycle in range(1, max_cycles + 1):
            if job.get("stop"):
                job["status"] = "stopped"
                break

            job["cycle"] = cycle
            job["status"] = "running"
            job["new_this_cycle"] = 0
            job["timeouts_this_cycle"] = 0

            # Snapshot corpus — exclude generated/topology wisdom keys.
            # Primary source policy defaults to Quran + YTheory + MachineLanguage.
            _GENERATED_PREFIXES = ("wisdom_loop_", "wisdom_ether_", "wisdom_digital_",
                                   "wisdom_space_", "wisdom_aether_", "wisdom_unity_", "wisdom_spirit_",
                                   )
            corpus_raw = await r.hgetall("guidance:corpus")
            _include = include_prefixes  # from job snapshot below
            entries = [
                (fid, json.loads(raw))
                for fid, raw in corpus_raw.items()
                if not any(fid.startswith(p) for p in _GENERATED_PREFIXES)
                and (not _include or any(fid.startswith(p) for p in _include))
            ]

            # If no explicit include_prefixes are provided, enforce primary-source-only
            # training so source/seed learning remains aligned to the core curriculum.
            if not _include:
                entries = [
                    (fid, entry)
                    for fid, entry in entries
                    if _is_primary_source_entry(fid, entry)
                ]
            if sort_by == 'revelation':
                entries.sort(key=_sort_key_revelation)
            elif sort_by == 'length':
                entries.sort(key=_sort_key_length)
            if max_entries:
                entries = entries[:max_entries]
            job["total_this_cycle"] = len(entries)
            job["current"] = 0
            job["current_title"] = ""

            async def _process_one(fid, entry, _cycle=cycle):
                content = entry.get("content", "").strip()
                if not content:
                    return None
                tip = await r.xrevrange("spirit:events", "+", "-", count=1)
                start_id = tip[0][0] if tip else "0-0"
                session_id = uuid.uuid4().hex
                await r.xadd("seed:input", {
                    "input_type": "text",
                    "content":    content[:50_000],
                    "source":     f"loop:c{_cycle}:{fid[:20]}",
                    "session_id": session_id,
                    "ts":         datetime.now(timezone.utc).isoformat(),
                })
                output = await _wait_for_layer7(redis_url, session_id, start_id, timeout=360)
                return (fid, entry, session_id, output)

            async def _process_and_save(fid, entry, _cycle=cycle):
                """Process one entry and immediately save wisdom — so next entry sees it in corpus."""
                result = await _process_one(fid, entry, _cycle)
                if isinstance(result, Exception) or result is None:
                    job["timeouts_this_cycle"] = job.get("timeouts_this_cycle", 0) + 1
                    return
                fid_r, entry_r, session_id, output = result
                if not output:
                    job["timeouts_this_cycle"] = job.get("timeouts_this_cycle", 0) + 1
                    return
                # --- Affinity / coherence tracking ---
                scores = _parse_affinity(output)
                peak_aff = max(scores) if scores else 0
                if scores:
                    job.setdefault("_cycle_affinity", []).append(peak_aff)
                    all_aff = job.get("_all_affinity", []) + [peak_aff]
                    job["_all_affinity"] = all_aff[-500:]
                    job["mean_coherence"] = round(sum(all_aff) / len(all_aff), 1)
                    job["peak_coherence"] = max(all_aff)
                    job["coherence_level"] = _coherence_level(job["mean_coherence"])
                new_fid = f"wisdom_loop_c{_cycle}_{session_id[:12]}"
                title = f"[Loop c{_cycle}] {entry_r.get('title', fid_r)[:80]}"
                await r.hset("guidance:corpus", new_fid, json.dumps({
                    "title":        title,
                    "content":      output,
                    "source":       f"loop:c{_cycle}:from:{fid_r}",
                    "ts":           datetime.now(timezone.utc).isoformat(),
                    "chars":        len(output),
                    "peak_affinity": peak_aff,
                }))
                await r.sadd("guidance:index", new_fid)
                _append_wisdom_disk(session_id, title, output, f"loop_c{_cycle}")
                job["new_this_cycle"] = job.get("new_this_cycle", 0) + 1
                job["total_produced"] = job.get("total_produced", 0) + 1

            # ----------------------------------------------------------------
            # FIBONACCI PULSE mode:
            #   - Split entries into group_a (include_prefixes) and group_b (group_b_prefixes)
            #   - Process in Fibonacci-sized pulses: 1, 1, 2, 3, 5, 8, 13...
            #   - Each pulse alternates direction (ascending / descending) = oscillation
            #   - Within each pulse: SEQUENTIAL (not parallel) — each entry's wisdom
            #     accumulates in corpus before the next entry sees it
            #   - Between group_a and group_b: Fibonacci ratio F(n):F(n-1)
            # ----------------------------------------------------------------
            if sort_by == 'fibonacci_pulse':
                def _fib_sequence():
                    a, b = 1, 1
                    while True:
                        yield a
                        a, b = b, a + b

                _group_b = group_b_prefixes or []
                if _group_b:
                    group_a_entries = [(f, e) for f, e in entries if any(f.startswith(p) for p in (include_prefixes or []))]
                    group_b_entries = [(f, e) for f, e in entries if any(f.startswith(p) for p in _group_b)]
                    # Interleave: build ordered pulse sequence alternating A and B in Fibonacci ratio
                    fib = _fib_sequence()
                    pulse_sequence = []
                    a_idx, b_idx = 0, 0
                    fn_prev, fn_curr = 1, 1
                    pulse_num = 0
                    while a_idx < len(group_a_entries) or b_idx < len(group_b_entries):
                        fn = next(fib)
                        # Odd pulse: take fn from group_a; Even pulse: take fn from group_b
                        if pulse_num % 2 == 0:
                            chunk = group_a_entries[a_idx:a_idx + fn]
                            a_idx += fn
                        else:
                            chunk = group_b_entries[b_idx:b_idx + fn]
                            b_idx += fn
                        if chunk:
                            # Oscillate direction: ascending on even pulse, descending on odd
                            pulse_sequence.append((pulse_num, chunk if pulse_num % 2 == 0 else list(reversed(chunk))))
                        pulse_num += 1
                        if a_idx >= len(group_a_entries) and b_idx >= len(group_b_entries):
                            break
                    pulse_entries = pulse_sequence
                else:
                    # Single stream: just Fibonacci-sized pulses with oscillation
                    fib = _fib_sequence()
                    idx = 0
                    pulse_entries = []
                    pulse_num = 0
                    while idx < len(entries):
                        fn = next(fib)
                        chunk = entries[idx:idx + fn]
                        if chunk:
                            direction_chunk = chunk if pulse_num % 2 == 0 else list(reversed(chunk))
                            pulse_entries.append((pulse_num, direction_chunk))
                        idx += fn
                        pulse_num += 1

                job["total_this_cycle"] = sum(len(c) for _, c in pulse_entries)
                for pulse_num, pulse_chunk in pulse_entries:
                    if job.get("stop"):
                        break
                    direction = "▲" if pulse_num % 2 == 0 else "▼"
                    job["pulse"] = pulse_num + 1
                    job["pulse_direction"] = "ascending" if pulse_num % 2 == 0 else "descending"
                    job["current_title"] = f"{direction} Pulse {pulse_num+1} [{len(pulse_chunk)} entries]"
                    for fid, entry in pulse_chunk:
                        if job.get("stop"):
                            break
                        job["current"] = job.get("current", 0) + 1
                        job["current_title"] = f"{direction} P{pulse_num+1}: {entry.get('title', fid)[:70]}"
                        # Sequential — await each one before proceeding
                        await _process_and_save(fid, entry, cycle)

            else:
                # ---- Original fixed-batch parallel mode ----
                for batch_start in range(0, len(entries), _BATCH):
                    if job.get("stop"):
                        break

                    batch = entries[batch_start:batch_start + _BATCH]
                    job["current"] = batch_start + len(batch)
                    job["current_title"] = batch[0][1].get("title", batch[0][0])[:80]

                    results = await asyncio.gather(
                        *[_process_one(fid, entry) for fid, entry in batch],
                        return_exceptions=True,
                    )

                    for result in results:
                        if isinstance(result, Exception) or result is None:
                            job["timeouts_this_cycle"] = job.get("timeouts_this_cycle", 0) + 1
                            continue
                        fid, entry, session_id, output = result
                        if not output:
                            job["timeouts_this_cycle"] = job.get("timeouts_this_cycle", 0) + 1
                            continue
                        scores = _parse_affinity(output)
                        peak_aff = max(scores) if scores else 0
                        if scores:
                            job.setdefault("_cycle_affinity", []).append(peak_aff)
                            all_aff = job.get("_all_affinity", []) + [peak_aff]
                            job["_all_affinity"] = all_aff[-500:]
                            job["mean_coherence"] = round(sum(all_aff) / len(all_aff), 1)
                            job["peak_coherence"] = max(all_aff)
                            job["coherence_level"] = _coherence_level(job["mean_coherence"])
                        new_fid = f"wisdom_loop_c{cycle}_{session_id[:12]}"
                        title = f"[Loop c{cycle}] {entry.get('title', fid)[:80]}"
                        await r.hset("guidance:corpus", new_fid, json.dumps({
                            "title":        title,
                            "content":      output,
                            "source":       f"loop:c{cycle}:from:{fid}",
                            "ts":           datetime.now(timezone.utc).isoformat(),
                            "chars":        len(output),
                            "peak_affinity": peak_aff,
                        }))
                        await r.sadd("guidance:index", new_fid)
                        _append_wisdom_disk(session_id, title, output, f"loop_c{cycle}")
                        job["new_this_cycle"] = job.get("new_this_cycle", 0) + 1
                        job["total_produced"] = job.get("total_produced", 0) + 1

            job["cycles_done"] = cycle

            # --- Persist cycle coherence to Redis coherence_matrix ---
            cycle_aff = job.pop("_cycle_affinity", [])
            if cycle_aff:
                cycle_coh = round(sum(cycle_aff) / len(cycle_aff), 1)
                entry_data = {
                    "cycle": cycle,
                    "mean_affinity": cycle_coh,
                    "peak_affinity": max(cycle_aff),
                    "wisdom_count":  len(cycle_aff),
                }
                job.setdefault("coherence_history", []).append(entry_data)
                await r.hset(
                    "topology:coherence_matrix",
                    f"cycle_{cycle}",
                    json.dumps(entry_data),
                )

            # Convergence: 0 new outputs means topology has absorbed all patterns
            # High coherence (≥70) with stable output = mind is fully aligned
            if job.get("new_this_cycle", 0) == 0 and not job.get("stop"):
                job["status"] = "converged"
                job["converged"] = True
                break

        if job["status"] == "running":
            job["status"] = "complete"

    except asyncio.CancelledError:
        job["status"] = "stopped"
        job["error"] = "Server restarted while loop was running — restart the loop"
        raise
    except Exception as exc:
        job["status"] = "error"
        job["error"] = str(exc)
    finally:
        try:
            await r.aclose()
        except Exception:
            pass
        job["finished_at"] = datetime.now(timezone.utc).isoformat()


class TrainingStartBody(BaseModel):
    max_cycles: int = 10
    max_entries: int = 300  # base corpus entries per cycle (excludes loop-generated)
    sort_by: str = "default"  # default | revelation | length | fibonacci_pulse
    include_prefixes: list[str] = []  # if set, ONLY include entries whose key starts with one of these (overrides primary-source default)
    group_b_prefixes: list[str] = []  # second stream for fibonacci_pulse interleaving (e.g. quran_surah_)


@router.post("/admin/training/start")
async def admin_training_start(body: TrainingStartBody):
    """Start a knowledge absorption training loop.

    Each cycle feeds every corpus entry through the full 7-layer topology,
    captures Layer 7 output, and saves it back as new corpus knowledge.
    Runs until convergence (0 new outputs) or max_cycles.
    """
    # Stop any running job first
    for jid, j in _training_jobs.items():
        if j.get("status") == "running":
            j["stop"] = True

    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    job_id = uuid.uuid4().hex
    _training_jobs[job_id] = {
        "job_id":        job_id,
        "status":        "starting",
        "cycle":         0,
        "cycles_done":   0,
        "max_cycles":    body.max_cycles,
        "total_this_cycle": 0,
        "new_this_cycle":   0,
        "total_produced":   0,
        "timeouts_this_cycle": 0,
        "current":       0,
        "current_title": "",
        "converged":     False,
        "sort_by":       body.sort_by,
        "pulse":         0,
        "pulse_direction": "",
        # Coherence / affinity tracking
        "mean_coherence":   0.0,   # mean peak-affinity across all wisdoms produced
        "peak_coherence":   0,     # highest single affinity seen
        "coherence_level":  "weak",
        "coherence_history": [],   # [{cycle, mean_affinity, peak_affinity, wisdom_count}, ...]
        "started_at":    datetime.now(timezone.utc).isoformat(),
    }
    asyncio.create_task(_run_training_loop(job_id, redis_url, body.max_cycles, body.max_entries, body.sort_by, body.include_prefixes, body.group_b_prefixes))
    return {"ok": True, "job_id": job_id}


@router.get("/admin/training/status")
async def admin_training_status():
    """Return the status of all training loop jobs (latest first)."""
    jobs = sorted(_training_jobs.values(), key=lambda j: j.get("started_at", ""), reverse=True)
    # Exclude internal tracking keys from the API response
    cleaned = []
    for j in jobs[:20]:
        cleaned.append({k: v for k, v in j.items() if not k.startswith("_")})
    return {"jobs": cleaned}


@router.get("/admin/coherence")
async def admin_coherence(redis=Depends(get_redis)):
    """Return the topology coherence matrix — affinity history across training cycles.

    Coherence = mean peak-affinity of wisdoms produced each cycle.
    Increasing coherence = the corpus is resonating more deeply with new inputs.
    High coherence (≥70) = the mind has internalized the pattern space.

    Also returns the live depth_config (dynamic MAX_LAYERS expansion state).
    """
    matrix_raw = await redis.hgetall("topology:coherence_matrix")
    depth_raw = await redis.hgetall("topology:depth_config")

    history = []
    for key in sorted(matrix_raw.keys()):
        try:
            history.append(json.loads(matrix_raw[key]))
        except Exception:
            pass

    # Running job coherence (live)
    live = None
    for j in sorted(_training_jobs.values(), key=lambda x: x.get("started_at", ""), reverse=True):
        if j.get("status") == "running":
            live = {
                "mean_coherence":  j.get("mean_coherence", 0),
                "peak_coherence":  j.get("peak_coherence", 0),
                "coherence_level": j.get("coherence_level", "weak"),
                "total_produced":  j.get("total_produced", 0),
                "cycle":           j.get("cycle", 0),
            }
            break

    return {
        "ok":           True,
        "history":      history,
        "depth_config": depth_raw,
        "live":         live,
        "interpretation": {
            "weak":                "< 5 — topology exploring, low pattern overlap",
            "moderate-resonance":  "5–20 — pattern recognition forming",
            "strong-convergence":  "20–50 — corpus aligning with input patterns",
            "high-coherence":      "≥ 50 — deep internalization, mind approaching synthesis",
        },
    }


@router.post("/admin/training/stop")
async def admin_training_stop():
    """Signal the running training loop to stop after the current entry."""
    stopped = 0
    for j in _training_jobs.values():
        if j.get("status") == "running":
            j["stop"] = True
            stopped += 1
    return {"ok": True, "stopped": stopped}


def _clean_text(text: str) -> str:
    """
    Strip non-meaningful formatting artifacts before seeding into the topology.
    Handles: Obsidian wikilinks/embeds, LaTeX block/inline equations, Markdown
    syntax, YAML frontmatter, callout blocks, HTML tags, and control characters.
    """
    import re

    # --- YAML frontmatter (---...---) at top of file ---
    text = re.sub(r"^---[\s\S]*?---\s*", "", text, count=1)

    # --- Obsidian: ![[embed]] and [[wikilink|alias]] / [[wikilink]] ---
    text = re.sub(r"!\[\[.*?\]\]", "", text)                    # embeds
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text) # [[link|alias]] → alias
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)             # [[link]] → link

    # --- LaTeX block equations: $$...$$ or \[...\] ---
    text = re.sub(r"\$\$[\s\S]*?\$\$", " ", text)
    text = re.sub(r"\\\[[\s\S]*?\\\]", " ", text)

    # --- LaTeX inline: $...$ (single dollar, non-empty, no newline inside) ---
    text = re.sub(r"\$[^\n$]{1,200}?\$", " ", text)

    # --- LaTeX commands: \command{...} or standalone \word ---
    text = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", " ", text)
    text = re.sub(r"\\[a-zA-Z]+", " ", text)

    # --- Obsidian callout blocks: > [!note] / > [!warning] etc ---
    text = re.sub(r"^> \[![^\]]+\].*$", "", text, flags=re.MULTILINE)

    # --- Markdown headings: # ## ### → keep text ---
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    # --- Markdown bold/italic: **text**, *text*, __text__, _text_ ---
    text = re.sub(r"\*{1,3}([^*\n]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_\n]+)_{1,3}", r"\1", text)

    # --- Markdown code blocks: ```...``` and inline `code` ---
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`[^`\n]*`", " ", text)

    # --- Markdown links: [text](url) → text; bare URLs ---
    text = re.sub(r"\[([^\]]+)\]\([^\)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", " ", text)

    # --- HTML tags ---
    text = re.sub(r"<[^>]{1,200}>", " ", text)

    # --- Horizontal rules: ---, ***, ___ ---
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)

    # --- Table separators: |---|---| rows ---
    text = re.sub(r"^\|?[\s\-|:]+\|[\s\-|:]+\|?\s*$", "", text, flags=re.MULTILINE)

    # --- Markdown blockquotes: leading > ---
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)

    # --- Bullet/numbered list markers: - item, * item, 1. item ---
    text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\s]*\d+\.\s+", "", text, flags=re.MULTILINE)

    # --- Control characters (except \n \r \t) ---
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # --- Unicode replacement character ---
    text = text.replace("\ufffd", "")

    # --- Collapse excessive blank lines (3+ → 2) ---
    text = re.sub(r"\n{3,}", "\n\n", text)

    # --- Collapse excessive spaces ---
    text = re.sub(r"[ \t]{3,}", "  ", text)

    return text.strip()


def _extract_text(filename: str, data: bytes) -> str:
    """Extract plain text from uploaded file bytes, then clean formatting artifacts."""
    name = filename.lower()

    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            pages = [p.extract_text() or "" for p in reader.pages]
            raw = "\n\n".join(pages).strip()
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"PDF parse error: {e}")
        return _clean_text(raw)

    if name.endswith((".txt", ".md", ".rst", ".csv", ".json", ".xml", ".yaml", ".yml")):
        raw = data.decode("utf-8", errors="replace").strip()
        return _clean_text(raw)

    if name.endswith((".html", ".htm")):
        try:
            from bs4 import BeautifulSoup
            raw = BeautifulSoup(data, "html.parser").get_text(separator=" ").strip()
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"HTML parse error: {e}")
        return _clean_text(raw)

    # Fallback: try UTF-8 decode
    try:
        raw = data.decode("utf-8", errors="replace").strip()
        return _clean_text(raw)
    except Exception:
        raise HTTPException(status_code=415, detail=f"Unsupported file type: {filename}")


@router.delete("/admin/guidance/{file_id}")
async def admin_delete_guidance(file_id: str, redis=Depends(get_redis)):
    """Remove one entry from guidance:corpus (and from guidance:index)."""
    deleted = await redis.hdel("guidance:corpus", file_id)
    await redis.srem("guidance:index", file_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Guidance entry not found")
    return {"ok": True, "deleted": file_id}


@router.post("/admin/clean-corpus")
async def admin_clean_corpus(redis=Depends(get_redis)):
    """
    Retroactively clean all seed/anchor corpus entries — strips Obsidian format,
    LaTeX equations, markdown syntax, and control characters from stored content.
    Skips wisdom_loop_, wisdom_ether_, wisdom_digital_, quran_surah_ entries.
    """
    _SKIP_PREFIXES = (
        "wisdom_loop_", "wisdom_ether_", "wisdom_digital_",
        "wisdom_space_", "wisdom_aether_", "wisdom_unity_", "wisdom_spirit_",
        "quran_surah_",
    )
    corpus_raw = await redis.hgetall("guidance:corpus")
    cleaned = 0
    skipped = 0
    for fid, raw in corpus_raw.items():
        if any(fid.startswith(p) for p in _SKIP_PREFIXES):
            skipped += 1
            continue
        try:
            entry = json.loads(raw)
        except Exception:
            skipped += 1
            continue
        original = entry.get("content", "")
        cleaned_content = _clean_text(original)
        if cleaned_content != original:
            entry["content"] = cleaned_content
            entry["chars"] = len(cleaned_content)
            await redis.hset("guidance:corpus", fid, json.dumps(entry))
            cleaned += 1
    return {"ok": True, "cleaned": cleaned, "skipped": skipped, "total": len(corpus_raw)}



class GuidanceEdit(BaseModel):
    title: str = ""
    content: str


@router.put("/admin/guidance/{file_id}")
async def admin_update_guidance(file_id: str, body: GuidanceEdit, redis=Depends(get_redis)):
    """Update title and/or content of any guidance:corpus entry."""
    raw = await redis.hget("guidance:corpus", file_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Guidance entry not found")
    entry = json.loads(raw)
    if body.title:
        entry["title"] = body.title
    entry["content"] = body.content
    entry["chars"] = len(body.content)
    entry["edited_at"] = datetime.now(timezone.utc).isoformat()
    await redis.hset("guidance:corpus", file_id, json.dumps(entry))
    return {"ok": True, "file_id": file_id, "chars": entry["chars"]}


@router.post("/admin/save-wisdom")
async def admin_save_wisdom(redis=Depends(get_redis)):
    """Harvest layer_done outputs from spirit:events and store each session's
    Convergence (layer7) output back into guidance:corpus as a wisdom entry.

    Safe to call before a wipe — wisdom persists as corpus knowledge.
    Returns count of new wisdom entries saved.
    """
    try:
        raw = await redis.xrevrange("spirit:events", "+", "-", count=2000)
    except Exception:
        return {"ok": True, "saved": 0, "message": "spirit:events empty"}

    # Collect best output per session from layer7 events
    wisdom_by_session: dict[str, dict] = {}
    for msg_id, fields in raw:
        if fields.get("type") != "layer_done":
            continue
        if str(fields.get("layer_num", "")) != "7":
            continue
        session_id = fields.get("session_id", "")
        if not session_id or session_id in wisdom_by_session:
            continue
        output = fields.get("output", "").strip()
        if len(output) < 50:
            continue
        wisdom_by_session[session_id] = {
            "session_id": session_id,
            "output":     output,
            "topic":      fields.get("topic", "")[:120],
            "ts":         fields.get("ts", datetime.now(timezone.utc).isoformat()),
        }

    saved = 0
    for session_id, w in wisdom_by_session.items():
        file_id = f"wisdom_{session_id}"
        # Skip if already in corpus
        existing = await redis.hget("guidance:corpus", file_id)
        if existing:
            continue
        entry = {
            "title":   f"Wisdom: {w['topic'] or session_id[:12]}",
            "content": w["output"],
            "source":  f"spirit:events (session {session_id[:8]})",
            "ts":      w["ts"],
            "chars":   len(w["output"]),
        }
        await redis.hset("guidance:corpus", file_id, json.dumps(entry))
        await redis.sadd("guidance:index", file_id)
        saved += 1

    return {"ok": True, "saved": saved, "sessions_found": len(wisdom_by_session)}


class WipeBody(BaseModel):
    confirm: str  # must be "WIPE" to proceed
    keep_wisdom: bool = True  # if True, save wisdom before wiping


@router.post("/admin/wipe")
async def admin_wipe(body: WipeBody, redis=Depends(get_redis)):
    """Full Redis state reset.

    Clears: seed:input, space:layer1-7, spirit:events, guidance:events,
            guidance:corpus, guidance:index.

    If keep_wisdom=True (default), wisdom is harvested from spirit:events
    into guidance:corpus BEFORE wiping, so it survives the reset.

    Requires body.confirm == "WIPE".
    """
    if body.confirm != "WIPE":
        raise HTTPException(status_code=400, detail='Send {"confirm": "WIPE"} to proceed')

    result: dict = {"ok": True, "kept_wisdom": 0, "cleared_keys": []}

    # 1. Optionally save wisdom first
    if body.keep_wisdom:
        wisdom_resp = await admin_save_wisdom(redis)
        result["kept_wisdom"] = wisdom_resp.get("saved", 0)

    # 2. Delete streams
    stream_keys = [
        "seed:input",
        "space:layer1", "space:layer2", "space:layer3",
        "space:layer4", "space:layer5", "space:layer6", "space:layer7",
        "spirit:events",
        "guidance:events",
    ]
    for key in stream_keys:
        try:
            await redis.delete(key)
            result["cleared_keys"].append(key)
        except Exception:
            pass

    # 3. Rebuild consumer groups so workers reconnect cleanly
    for stream_key in ["seed:input", "space:layer1", "space:layer2", "space:layer3",
                       "space:layer4", "space:layer5", "space:layer6", "space:layer7"]:
        try:
            group = stream_key.replace(":", "_") + "_minds"
            if stream_key == "seed:input":
                group = "seed_minds"
            await redis.xgroup_create(stream_key, group, id="$", mkstream=True)
        except Exception:
            pass  # group already exists or stream recreated

    # 4. Wipe guidance corpus — always preserve sacred entries (foundation: and quran_surah_)
    #    (wisdom save already wrote to corpus above)
    _SACRED = ("foundation:", "quran_surah_")
    raw = await redis.hgetall("guidance:corpus")
    if not body.keep_wisdom:
        to_delete = [fid for fid in raw if not any(fid.startswith(p) for p in _SACRED)]
        if to_delete:
            await redis.hdel("guidance:corpus", *to_delete)
            await redis.delete("guidance:index")
        result["cleared_keys"].append(f"guidance:corpus ({len(to_delete)} non-sacred entries)")
        result["cleared_keys"].append("guidance:index")
    else:
        # Clear only non-wisdom, non-sacred entries
        to_delete = [fid for fid in raw
                     if not fid.startswith("wisdom_")
                     and not any(fid.startswith(p) for p in _SACRED)]
        if to_delete:
            await redis.hdel("guidance:corpus", *to_delete)
            # Also clear guidance:index so scanner re-ingests
            await redis.delete("guidance:index")
            result["cleared_keys"].append(f"guidance:corpus ({len(to_delete)} non-wisdom non-sacred entries)")
            result["cleared_keys"].append("guidance:index")

    return result


@router.post("/admin/upload-to-seed")
async def admin_upload_to_seed(
    file: UploadFile = File(...),
    redis=Depends(get_redis),
):
    """Upload a file, extract its text, push the content to seed:input."""
    if file.size and file.size > 10 * 1024 * 1024:  # 10 MB guard
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    data = await file.read()
    content = _extract_text(file.filename or "file.txt", data)

    if not content:
        raise HTTPException(status_code=422, detail="No text content could be extracted")

    session_id = uuid.uuid4().hex
    msg_id = await redis.xadd(
        "seed:input",
        {
            "input_type":  "text",
            "content":     content[:50_000],   # cap at 50k chars
            "source":      f"upload:{file.filename}",
            "session_id":  session_id,
            "ts":          datetime.now(timezone.utc).isoformat(),
        },
    )
    return {
        "ok":         True,
        "filename":   file.filename,
        "chars":      len(content),
        "msg_id":     msg_id,
        "session_id": session_id,
    }
