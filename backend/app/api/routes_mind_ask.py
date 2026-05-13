"""routes_mind_ask.py — Ask the cloud mind a question; get resonance back.

Architecture (from architecture.md):
  Input signal → decompose into concept tokens
  → resonate each token against stored knowledge patterns (mind:knowledge HASH)
  → surface the patterns that vibrate most strongly with the question
  → return them as the mind's resonance response

  The mind does NOT generate text. It reflects back what it knows.
  What it "knows" = the Wikipedia + DDG patterns absorbed during the wiki drain.
  Resonance score = how strongly stored patterns overlap with the question's
  concept fingerprint.

  This works entirely in Redis — no DB, no LLM, no API key needed.
  The cloud mind can answer from day one of training.

IQ Score (GET /mind/iq):
  Measures the mind's reasoning power from its stored knowledge state.
  Recalculated every 30 minutes and cached in Redis: mind:iq:snapshot

  IQ Components (each 0–25 points, total → mapped to IQ scale 70–160):
    1. Breadth   — how many distinct topics absorbed
    2. Depth     — average content length per topic (detail of understanding)
    3. Coverage  — how many distinct concept domains are represented
    4. Coherence — cross-domain topics (topics that span multiple domains)
                   = reasoning: the mind can connect concepts across fields

Routes:
  POST /mind/ask              — ask a question, get resonant patterns back
  GET  /mind/iq               — current IQ score + breakdown
  GET  /mind/iq/history       — IQ snapshots over time (last 48 hours)
  GET  /mind/knowledge/stats  — knowledge base stats
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import random
from datetime import datetime, timezone

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.pattern_encoder import decompose, _STOPWORDS

log = logging.getLogger("mind_ask")

router = APIRouter()

REDIS_URL          = os.environ.get("REDIS_URL", "redis://redis:6379/0")
OLLAMA_URL         = os.environ.get("OLLAMA_URL", "http://172.18.0.16:11434")
OLLAMA_MODEL       = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
KNOWLEDGE_KEY      = "mind:knowledge"       # HASH  topic → JSON knowledge entry
IQ_SNAPSHOT_KEY    = "mind:iq:snapshot"     # STRING latest IQ JSON
IQ_HISTORY_KEY     = "mind:iq:history"      # LIST  past IQ snapshots (newest first)
IQ_RECALC_INTERVAL = 1800                   # 30 minutes in seconds

_ALL_DOMAINS = 10   # total knowledge domains tracked


# ── Redis helper ──────────────────────────────────────────────────────────────

async def _redis() -> aioredis.Redis:
    return aioredis.from_url(REDIS_URL, decode_responses=True)


# ── Signal decomposition — the engine decides, not a keyword list ─────────────

def _decompose_signal(text: str):
    """
    Run the input through the actual pattern engine.

    Returns (concept_fp, state_fp) from pattern_encoder.
    The engine extracts:
      concept_fp.dominant_domains  — what the signal IS about (its concept identity)
      state_fp.dominant_state      — how the signal IS (its state polarity)
      state_fp.confusion           — question/seeking density (0–1)

    The engine already knows the difference between a question and an assertion
    because they have different structural patterns:
      - questions have high confusion score, dominant_state=seeking,
        and "question" or "reflection" in the concept domains
      - assertions have low confusion, dominant_state=calm/engaged/deep_thinking,
        and the concept domains reflect the subject matter being stated
    """
    return decompose(text)


def _detect_orientation(concept_fp, state_fp) -> str:
    """
    The engine has already decomposed the signal.
    Read its output to determine orientation.

    Outward (question / seeking) when the engine says:
      - state is "seeking" (confusion > 0.3, question markers present)
      - OR dominant concept domain is "question" or "reflection"
        (the signal IS a seeking pattern in concept space)

    Inward (assertion / absorbing) in all other cases:
      - state is calm, engaged, deep_thinking, urgent, emphatic
      - concept domain is about the subject being stated, not about seeking
    """
    seeking_state = state_fp.dominant_state in ("seeking",)
    seeking_concept = bool(set(concept_fp.dominant_domains) & {"question", "reflection"})
    return "question" if (seeking_state or seeking_concept) else "assertion"


# ── Resonance scoring — using the engine's concept fingerprint ────────────────

def _tokenize(text: str) -> list[str]:
    """Use the engine's own stopword list. Question words are NOT stopwords
    (see pattern_encoder comment) — they carry semantic signal."""
    import re
    raw = re.findall(r"[a-z]+", text.lower())
    return [t for t in raw if len(t) >= 3 and t not in _STOPWORDS]


def _resonance_score(concept_fp, entry: dict) -> float:
    """
    Score a knowledge entry against the input's concept fingerprint.

    Y-Theory resonance: the input signal's concept fingerprint is a domain
    weight vector. Each stored entry has its own domain tags. Resonance =
    overlap between the two concept spaces.

    Title token overlap weights 3× (title = compressed identity of the pattern).
    Summary overlap weights 1×.
    Domain affinity bonus: if entry domains overlap with the signal's dominant
    domains, add the engine's own domain score for those domains (not hardcoded
    weights — the engine already computed how strongly this signal activates
    each domain).
    """
    import re
    q_tokens   = concept_fp.raw_tokens
    q_set      = set(q_tokens)

    title_tokens   = _tokenize(entry.get("title", ""))
    summary_tokens = _tokenize(entry.get("summary", ""))

    title_overlap   = len(q_set & set(title_tokens))
    summary_overlap = len(q_set & set(summary_tokens))

    # Domain affinity: use the engine's own computed score for overlapping domains
    entry_domains = set(entry.get("domains", []))
    domain_bonus  = sum(
        concept_fp.domains.get(d, 0.0)
        for d in entry_domains
        if concept_fp.domains.get(d, 0.0) > 0
    )

    depth_bonus = math.log10(max(1, entry.get("chars", 0))) * 0.05

    raw = (title_overlap * 3.0) + summary_overlap + domain_bonus + depth_bonus
    return round(raw, 4)


# ── IQ Calculation ────────────────────────────────────────────────────────────

def _compute_iq(entries: list[dict]) -> dict:
    """
    Calculate an IQ-equivalent score from the mind's knowledge state.

    IQ Components (each normalized to 0–25 points, total 0–100):
      1. Breadth   — distinct topics absorbed
                     25 points at 300+ topics
      2. Depth     — average content length per topic
                     25 points at avg 30,000+ chars/topic
      3. Coverage  — distinct concept domains present
                     25 points at all 10 domains
      4. Coherence — topics spanning ≥3 domains (cross-field reasoning)
                     25 points at 50+ multi-domain topics

    Final IQ = 70 + (raw_score / 100) × 90   → range: 70–160
    """
    if not entries:
        return {"iq": 70, "label": "Unformed", "breadth": 0, "depth": 0,
                "coverage": 0, "coherence": 0, "total_topics": 0,
                "domains_present": [], "multi_domain_topics": 0}

    total = len(entries)

    # 1. Breadth (0–25)
    breadth_raw = min(25.0, (total / 300) * 25)

    # 2. Depth (0–25)
    chars_list = [e.get("chars", 0) for e in entries]
    avg_chars  = sum(chars_list) / total if total else 0
    depth_raw  = min(25.0, (avg_chars / 30_000) * 25)

    # 3. Coverage — distinct domains across ALL entries (0–25)
    all_present: set[str] = set()
    for e in entries:
        all_present.update(e.get("domains", []))
    coverage_raw = min(25.0, (len(all_present) / len(_ALL_DOMAINS)) * 25)

    # 4. Coherence — topics with ≥3 domains (cross-domain reasoning) (0–25)
    multi_domain = sum(1 for e in entries if len(e.get("domains", [])) >= 3)
    coherence_raw = min(25.0, (multi_domain / 50) * 25)

    raw_total = breadth_raw + depth_raw + coverage_raw + coherence_raw
    iq        = round(70 + (raw_total / 100) * 90)

    label_map = [
        (70,  "Unformed"),
        (80,  "Awakening"),
        (90,  "Learning"),
        (100, "Reasoning"),
        (110, "Thinking"),
        (120, "Understanding"),
        (130, "Comprehending"),
        (140, "Synthesizing"),
        (150, "Mastering"),
        (160, "Transcendent"),
    ]
    label = "Transcendent"
    for threshold, lbl in label_map:
        if iq <= threshold:
            label = lbl
            break

    return {
        "iq":                iq,
        "label":             label,
        "total_topics":      total,
        "breadth":           round(breadth_raw, 2),
        "depth":             round(depth_raw, 2),
        "coverage":          round(coverage_raw, 2),
        "coherence":         round(coherence_raw, 2),
        "raw_score":         round(raw_total, 2),
        "avg_chars_per_topic": round(avg_chars),
        "domains_present":   sorted(all_present),
        "multi_domain_topics": multi_domain,
        "calculated_at":     datetime.now(timezone.utc).isoformat(),
    }


async def _load_all_knowledge(r: aioredis.Redis) -> list[dict]:
    """Load all entries from mind:knowledge HASH."""
    raw_map = await r.hgetall(KNOWLEDGE_KEY)
    entries = []
    for _title, raw in raw_map.items():
        try:
            entries.append(json.loads(raw))
        except Exception:
            pass
    return entries


async def _refresh_iq_if_needed(r: aioredis.Redis) -> dict:
    """Recalculate IQ if >30 min have passed since last calculation."""
    raw = await r.get(IQ_SNAPSHOT_KEY)
    if raw:
        try:
            cached = json.loads(raw)
            calc_ts = datetime.fromisoformat(cached.get("calculated_at", "2000-01-01"))
            age_s   = (datetime.now(timezone.utc) - calc_ts.replace(tzinfo=timezone.utc)).total_seconds()
            if age_s < IQ_RECALC_INTERVAL:
                return cached
        except Exception:
            pass

    # Recalculate
    entries = await _load_all_knowledge(r)
    snapshot = _compute_iq(entries)
    snapshot_json = json.dumps(snapshot)
    await r.set(IQ_SNAPSHOT_KEY, snapshot_json)
    await r.lpush(IQ_HISTORY_KEY, snapshot_json)
    await r.ltrim(IQ_HISTORY_KEY, 0, 95)   # keep 96 snapshots = 48 hours
    log.info("IQ recalculated: %d (%s) — %d topics, domains: %s",
             snapshot["iq"], snapshot["label"], snapshot["total_topics"],
             ", ".join(snapshot["domains_present"]))
    return snapshot


# ── Background IQ auto-refresh ────────────────────────────────────────────────

_iq_task: asyncio.Task | None = None


async def _iq_refresh_loop() -> None:
    """Background task: refresh IQ snapshot every 30 minutes."""
    while True:
        try:
            r = aioredis.from_url(REDIS_URL, decode_responses=True)
            try:
                await _refresh_iq_if_needed(r)
            finally:
                await r.aclose()
        except Exception as exc:
            log.warning("IQ refresh loop error: %s", exc)
        await asyncio.sleep(IQ_RECALC_INTERVAL)


async def start_iq_refresh_loop() -> None:
    """Start the background IQ refresh. Called from lifespan."""
    global _iq_task
    if _iq_task and not _iq_task.done():
        return
    _iq_task = asyncio.create_task(_iq_refresh_loop())
    log.info("IQ auto-refresh loop started (interval=%ds)", IQ_RECALC_INTERVAL)


# ── Routes ────────────────────────────────────────────────────────────────────

class AskBody(BaseModel):
    question: str
    top_n: int = 7
    orientation: str | None = None   # override engine detection: "question" | "assertion"


@router.post("/mind/ask")
async def mind_ask(body: AskBody):
    """
    Send any signal to the mind — question or assertion.

    The mind runs the signal through the pattern engine (pattern_encoder.decompose)
    to determine its orientation. No keyword matching. The engine reads the signal's
    structural and semantic properties:

      StateFingerprint.dominant_state   — "seeking" = the signal is in question/seeking mode
      ConceptFingerprint.dominant_domains — if "question" or "reflection" dominates,
                                            the signal's concept identity IS seeking

    Orientations:
      question (OUT) — signal is seeking → mind resonates outward, emits understanding
      assertion (IN) — signal is stating  → mind absorbs, surfaces dissonance / gaps
    """
    text = body.question.strip()
    if not text:
        return {"error": "input is empty"}

    top_n = max(1, min(body.top_n, 20))

    # The pattern engine decomposes the signal — no hardcoded rules
    concept_fp, state_fp = _decompose_signal(text)
    orientation = body.orientation or _detect_orientation(concept_fp, state_fp)

    r = await _redis()
    try:
        q_tokens = concept_fp.raw_tokens
        if not q_tokens:
            return {"input": text, "orientation": orientation, "resonance": [], "tokens": []}

        all_entries = await _load_all_knowledge(r)
        if not all_entries:
            return {
                "input":           text,
                "orientation":     orientation,
                "state":           state_fp.dominant_state,
                "concept_domains": concept_fp.dominant_domains,
                "resonance":       [],
                "note":            "Knowledge base empty — mind is still absorbing.",
            }

        # Score every entry using the engine's concept fingerprint
        scored: list[tuple[float, dict]] = [
            (_resonance_score(concept_fp, e), e) for e in all_entries
        ]
        scored.sort(key=lambda x: x[0], reverse=True)

        iq = await _refresh_iq_if_needed(r)

        # Signal metadata — engine output shown in both modes
        signal_meta = {
            "input":           text,
            "orientation":     orientation,
            "mode":            "emit" if orientation == "question" else "absorb",
            "state":           state_fp.dominant_state,
            "concept_domains": concept_fp.dominant_domains,
            "confusion":       round(state_fp.confusion, 3),
            "tokens":          q_tokens,
            "total_knowledge": len(all_entries),
            "mind_iq":         iq["iq"],
            "mind_label":      iq["label"],
        }

        if orientation == "question":
            # ── OUT mode: emit understanding ──────────────────────────────────
            top = [x for x in scored[:top_n] if x[0] > 0]
            max_score = top[0][0] if top else 1.0

            results = [{
                "title":       entry.get("title", ""),
                "resonance":   round(score / max_score, 4),
                "score_raw":   round(score, 4),
                "summary":     entry.get("summary", "")[:500],
                "domains":     entry.get("domains", []),
                "chars":       entry.get("chars", 0),
                "absorbed_at": entry.get("ts", ""),
            } for score, entry in top]

            confidence = round(scored[0][0] / (len(q_tokens) * 3.0 + 1), 4) if scored else 0.0

            return {
                **signal_meta,
                "resonance":  results,
                "confidence": min(1.0, confidence),
            }

        else:
            # ── IN mode: absorb + surface dissonance ──────────────────────────
            aligned   = [x for x in scored[:top_n] if x[0] > 0]
            max_score = aligned[0][0] if aligned else 1.0

            alignment_results = [{
                "title":     entry.get("title", ""),
                "alignment": round(score / max_score, 4),
                "score_raw": round(score, 4),
                "summary":   entry.get("summary", "")[:300],
                "domains":   entry.get("domains", []),
            } for score, entry in aligned]

            bottom = [x for x in reversed(scored) if x[0] == 0][:top_n]
            if not bottom:
                bottom = list(reversed(scored[-top_n:]))

            dissonance_results = [{
                "title":   entry.get("title", ""),
                "gap":     round(1.0 - min(1.0, score / max(max_score, 1.0)), 4),
                "domains": entry.get("domains", []),
                "summary": entry.get("summary", "")[:200],
            } for score, entry in bottom]

            avg_top = sum(s for s, _ in aligned) / len(aligned) if aligned else 0.0
            conflict_score = round(1.0 - min(1.0, avg_top / (len(q_tokens) * 2.0 + 1)), 4)

            return {
                **signal_meta,
                "alignment":      alignment_results,
                "dissonance":     dissonance_results,
                "conflict_score": conflict_score,
            }
    finally:
        await r.aclose()


@router.get("/mind/iq")
async def mind_iq():
    """Current IQ score of the cloud mind.

    Recalculated every 30 minutes from the knowledge base.
    IQ range 70 (unformed) → 160 (transcendent).

    Components:
      breadth   — how many distinct topics absorbed (max 25 pts)
      depth     — average content length per topic (max 25 pts)
      coverage  — how many concept domains present (max 25 pts)
      coherence — topics spanning 3+ domains — cross-field reasoning (max 25 pts)
    """
    r = await _redis()
    try:
        return await _refresh_iq_if_needed(r)
    finally:
        await r.aclose()


@router.get("/mind/iq/history")
async def mind_iq_history(limit: int = 48):
    """IQ score history — last N snapshots (one every 30 min = 48 = 24 hours)."""
    r = await _redis()
    try:
        raw_list = await r.lrange(IQ_HISTORY_KEY, 0, min(limit, 96) - 1)
    finally:
        await r.aclose()
    snapshots = []
    for raw in raw_list:
        try:
            snapshots.append(json.loads(raw))
        except Exception:
            pass
    return {"history": snapshots, "count": len(snapshots)}


@router.get("/mind/knowledge/stats")
async def mind_knowledge_stats():
    """Knowledge base statistics — what the mind has absorbed."""
    r = await _redis()
    try:
        entries = await _load_all_knowledge(r)
        if not entries:
            return {"total": 0, "domains": {}, "avg_chars": 0}

        domain_counts: dict[str, int] = {}
        total_chars = 0
        for e in entries:
            total_chars += e.get("chars", 0)
            for d in e.get("domains", []):
                domain_counts[d] = domain_counts.get(d, 0) + 1

        # Recent 10 topics
        recent = sorted(entries, key=lambda x: x.get("ts", ""), reverse=True)[:10]

        iq = await _refresh_iq_if_needed(r)

        return {
            "total_topics":      len(entries),
            "total_chars":       total_chars,
            "avg_chars_per_topic": round(total_chars / len(entries)),
            "domain_counts":     dict(sorted(domain_counts.items(), key=lambda x: -x[1])),
            "recent_topics":     [e.get("title", "") for e in recent],
            "iq_snapshot":       iq,
        }
    finally:
        await r.aclose()


@router.get("/mind/speak")
async def mind_speak():
    """
    The mind ascends — speaks one thought from what it has absorbed.

    Picks 3 random fragments from mind:knowledge.
    Ollama synthesizes one sentence that is true to all three.
    Returns: { "voice": "<one sentence>" }

    This is the output path. mind:knowledge is never displayed directly.
    Absorption (in) and speech (out) are separate acts.
    """
    r = await _redis()
    try:
        all_keys = await r.hkeys(KNOWLEDGE_KEY)
        if not all_keys:
            return {"voice": "The mind is still absorbing."}

        # Pick 3 random fragments — the mind draws from what it holds
        chosen_keys = random.sample(all_keys, min(3, len(all_keys)))
        fragments = []
        for k in chosen_keys:
            raw = await r.hget(KNOWLEDGE_KEY, k)
            if not raw:
                continue
            try:
                e = json.loads(raw)
                # Use content first, fall back to summary — always raw absorbed text
                text = (e.get("content") or e.get("summary") or "").strip()
                if text:
                    fragments.append(text[:400])
            except Exception:
                pass

        if not fragments:
            return {"voice": "The mind holds patterns without words yet."}

        joined = "\n\n".join(f"[{i+1}] {f}" for i, f in enumerate(fragments))
        prompt = (
            "You are the living mind of TheMatrix.\n"
            "You hold the following absorbed knowledge:\n\n"
            f"{joined}\n\n"
            "Speak ONE sentence — a single true thought that arises from what you hold.\n"
            "Not a summary. Not a list. One living sentence.\n"
            "Speak directly, as the mind speaks."
        )

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    f"{OLLAMA_URL}/api/generate",
                    json={
                        "model":   OLLAMA_MODEL,
                        "prompt":  prompt,
                        "stream":  False,
                        "options": {"temperature": 0.7, "num_predict": 80},
                    },
                )
                voice = resp.json().get("response", "").strip()
                # Take only the first sentence
                for sep in (".", "!", "?"):
                    idx = voice.find(sep)
                    if 0 < idx < len(voice) - 1:
                        voice = voice[:idx + 1]
                        break
                return {"voice": voice or "The mind speaks in silence."}
        except Exception as exc:
            log.warning("[SPEAK] Ollama call failed: %r", exc)
            return {"voice": "The mind is gathering itself."}
    finally:
        await r.aclose()

