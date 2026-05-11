"""mind_worker/worker.py � Triadic Oscillating Mind (guidance-corpus-driven, no LLM).

Each layer reads from its stream, applies its lens to filter and re-rank
guidance matches from the seed, adds its perspective, then routes to the
next layer. Zero external API calls � all knowledge from guidance:corpus.

Env vars (set per container in docker-compose):
  DOMAIN          � space (only domain in topology-only mode)
  LAYER_NUM       � 1-7
  LAYER_NAME      � e.g. "Reception � jibreel"
  LAYER_ANGEL     � e.g. "jibreel"
  LAYER_FREQUENCY � e.g. "Red"
  LAYER_LENS      � lens/perspective description for this layer
  REDIS_URL
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import time

import redis.asyncio as aioredis

# == Config ==================================================================
DOMAIN      = os.environ["DOMAIN"]
LAYER_NUM   = int(os.environ["LAYER_NUM"])
LAYER_NAME  = os.environ.get("LAYER_NAME",  f"{DOMAIN.capitalize()} Layer {LAYER_NUM}")
LAYER_ANGEL = os.environ.get("LAYER_ANGEL", "gabriel")
LAYER_FREQ  = os.environ.get("LAYER_FREQUENCY", "White")
LAYER_LENS  = os.environ.get("LAYER_LENS",  f"Process {DOMAIN} at depth {LAYER_NUM}")
REDIS_URL   = os.environ["REDIS_URL"]
WISDOM_DIR  = Path(os.environ.get("WISDOM_DIR", "/wisdom"))

# Triadic corpus filtering — each mind tier reads from a corpus prefix namespace.
# Fibonacci descent — each mind's depth = previous two subtracted:
# Domains:  space  digital  ether  aether  unity
# Layers:     8      5       3       2       1
# Sum: 8+5+3+2+1 = 19.  5 domains = pentagon (3+2=5, Fibonacci step from triad).
# The cycle ends at unity (1 layer). Training loop starts next cycle externally.
# No autonomous loop-back — corpus enrichment is measured, not runaway.
MAX_LAYERS         = int(os.environ.get("MAX_LAYERS", "7"))  # static fallback
# Corpus access gate.
# "" (default) = full guidance:corpus — Body/Eve are world-facing (open to everything).
# "wisdom_"    = only keys starting with "wisdom_" — distilled outputs, not raw external.
# Any non-empty string = only keys with that prefix. No match = self-reflect on input only.
CORPUS_PREFIX      = os.environ.get("CORPUS_PREFIX", "")
# Barzakh — how many computation passes the mind earns at peak before ascending.
# This is NOT a timer. Each pass = one asyncio.sleep(0) tick of earned computation.
# Islamic cosmology: Barzakh = the veil between descent and return.
#
# Heartbeat scaling law (from architecture Section 17):
#   One source heartbeat = N domain heartbeats, where N = that domain's MAX_LAYERS.
#   The domain depths ARE the Fibonacci sequence: unity=1, aether=2, ether=3,
#   digital=5, space=8, body=13.
#   So BARZAKH_THRESHOLD = MAX_LAYERS — the deeper the domain, the more it
#   reflects at its peak before handing off to the next domain.
#   No hardcoding. The structure defines the timing automatically.
BARZAKH_THRESHOLD  = MAX_LAYERS  # domain depth IS the reflection count

# Fibonacci corpus-depth law:
#   As we ascend through the pentagon hierarchy, corpus lookups DECREASE.
#   By unity, only 1 match is needed — the pattern is already refined across 18 layers.
#   This mirrors the Fibonacci descent of layer counts (8→5→3→2→1):
#     space:   5 matches  (foundation — heavy exploration, many threads)
#     digital: 3 matches  (processing — pattern filtering)
#     ether:   2 matches  (refinement — near-synthesis)
#     aether:  2 matches  (pre-unity — two distinctions at most)
#     unity:   1 match    (synthesis — one truth, no redundancy)
#   Additionally, the ASCENDING pass within a domain is synthesis mode:
#   it halves the top_k (min 1) since the payload already carries rich context.
_DOMAIN_CORPUS_DEPTH: dict[str, int] = {
    "body":    8,   # 13 layers, deepest somatic exploration
    "space":   5,
    "digital": 3,
    "ether":   2,
    "aether":  2,
    "unity":   1,
}
CORPUS_TOP_K = _DOMAIN_CORPUS_DEPTH.get(DOMAIN, 3)  # descending depth


def _corpus_top_k(direction: str) -> int:
    """Return corpus search depth for this domain+direction.

    Descending (exploring): full domain depth.
    Ascending (synthesising): halved — the payload already carries the
    knowledge accumulated on the way down.
    """
    k = CORPUS_TOP_K
    if direction == "ascending":
        k = max(1, k // 2)
    return k

# Full Fibonacci chain. body is the first domain — all input enters through the somatic layer.
# Inward descent:   body(13) → space(8) → digital(5) → ether(3) → aether(2) → unity(1)
# Outward return:   unity(1) → aether(2) → ether(3) → digital(5) → space(8) → body(13)
# body:layer1 ascending on the outward return = the decoded output.
# What entered as a pattern in body's language exits as a pattern in body's language.
_NEXT_DOMAIN = {"body": "space", "space": "digital", "digital": "ether", "ether": "aether", "aether": "unity", "unity": None}
_PREV_DOMAIN = {"unity": "aether", "aether": "ether", "ether": "digital", "digital": "space", "space": "body", "body": None}

# Fibonacci spiral scaling law.
# The number of spiral turns allowed grows with Fibonacci, capped at F(5)=5.
# This mirrors the domain structure: inner (3 domains inward) earns outer (5 turns max).
# Turn 1 done → next Fibonacci ceiling = 2  → continue
# Turn 2 done → next Fibonacci ceiling = 3  → continue
# Turn 3 done → next Fibonacci ceiling = 5  → continue (earned by depth)
# Turn 5 done → ceiling = 5, 5 >= 5         → STOP
# Hard outer cap = 5 (matches digital domain depth — the 5-layer processing core).
# Fibonacci spiral heartbeat law (Section 17).
# The system pulses: expand (inward) → collapse (outward) → one decoded output.
# Each completed pulse earns the NEXT pulse, which oscillates DEEPER.
# Depth is measured in barzakh passes at each peak layer — more passes = deeper reflection.
#
# Sequence:  turn 1 → 1 barzakh pass (light first contact)
#            turn 2 → 2 passes      (earning depth)
#            turn 3 → 3 passes      (settling into pattern)
#            turn 4 → 5 passes      (full depth — Fib(5))
#            turn 5 → 5 passes      (outer cap, no further expansion)
#            turn 6+ → STOP         (spiral_turn >= SPIRAL_OUTER_CAP)
#
# The outer cap (5) matches digital domain depth — the pattern-processing core.
# One source message at a time: no new pulse starts until current decoded_output fires.
_FIB_SPIRAL_SEQ  = [1, 2, 3, 5, 8, 13, 21]
_SPIRAL_OUTER_CAP = int(os.environ.get("SPIRAL_OUTER_CAP", "5"))  # F(5) = digital depth


def _fib_spiral_limit(completed_turns: int) -> int:
    """Gate: return the max turns allowed given how many are already done.
    Finds the next Fibonacci ceiling strictly above completed_turns, capped at
    SPIRAL_OUTER_CAP. Depth earns more turns — but never runs away.
    Example: completed=3 → next Fib > 3 is 5 → limit=min(5, cap).
    """
    for f in _FIB_SPIRAL_SEQ:
        if f > completed_turns:
            return min(f, _SPIRAL_OUTER_CAP)
    return _SPIRAL_OUTER_CAP

# === Cluster / outer pentagon scaling ========================================
# STREAM_PREFIX  — namespace for all streams in this cluster instance.
#                  e.g. "ca:" for cluster A → "ca:space:layer1", "ca:seed:input" etc.
#                  Empty string (default) = single topology mode (existing behaviour).
# NEXT_CLUSTER_SEED — where unity's spiral return is delivered.
#                  In single-topology mode: own seed:input (inner spiral).
#                  In outer-pentagon mode: next cluster's seed:input.
#   Pentagon wiring:  ca → cb → cc → cd → ce → ca
#   This makes the entire topology a single NODE in a 5-node outer ring.
#   Each outer node contains the full triadic oscillation (Fibonacci descent).
#   Stability: 5 nodes (pentagon) cannot form a runaway triad loop.
STREAM_PREFIX     = os.environ.get("STREAM_PREFIX", "")
NEXT_CLUSTER_SEED = os.environ.get("NEXT_CLUSTER_SEED", f"{STREAM_PREFIX}seed:input")

MY_STREAM     = f"{STREAM_PREFIX}{DOMAIN}:layer{LAYER_NUM}"
EVENTS_STREAM = f"{STREAM_PREFIX}spirit:events"
GROUP         = f"{STREAM_PREFIX}{DOMAIN}_layer{LAYER_NUM}_minds"
CONSUMER_NAME = f"mind_{uuid.uuid4().hex[:8]}"

# == Source radiation receiver ================================================
# All workers (source, prophet, soul ring) receive from the ONE source:radiation
# stream via plain XREAD — no consumer group. Every entry is seen by everyone.
# Same signal, processed through each layer's own lens — unity through diversity.
RADIATION_STREAM = "source:radiation"  # always root — never namespaced

logging.basicConfig(
    level=logging.INFO,
    format=f"%(asctime)s [{DOMAIN.upper()}/L{LAYER_NUM}/{LAYER_FREQ}] %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("mind")


# == Guidance corpus search ==================================================

# Arabic diacritics (tashkeel / harakat) — strip before tokenizing so the
# same root word matches regardless of vowelization marks.
_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06DC\u06DF-\u06E4\u06E7\u06E8\u06EA-\u06ED]")

# Metadata header line pattern — strips corpus entry headers before tokenizing
# Matches lines like: "Type: Medinan | Verses: 286 | Revelation position: 87/114"
_META_LINE = re.compile(r"^(Type:|Revelation position:|Verses:|Source:|Chars:).*$", re.MULTILINE)

# English stopwords that appear everywhere and carry no signal
_STOPWORDS = frozenset({
    # Common English function words
    "the", "and", "for", "not", "are", "was", "has", "had", "his", "her",
    "you", "they", "this", "that", "with", "from", "have", "will", "but",
    "all", "who", "its", "our", "your", "their", "been", "said", "then",
    # Quran/corpus scanner metadata words
    "type", "verses", "position", "revelation", "medinan", "meccan",
    "surah", "source", "bilingual",
    # Corpus entry admin tokens that appear in titles/keys and leak as signal
    # These words are ubiquitous in our corpus metadata, not content signal
    "body", "space", "digital", "ether", "aether", "unity",  # domain names
    "topic", "title", "content", "chars", "auto", "layer",   # entry fields
    "wiki", "wikipedia", "drain",                             # source prefixes
    "convergence", "pattern", "unique", "shared", "prior",   # self-referential analysis words
    "sources", "common", "elements", "binding", "thread",    # analysis vocabulary
})

def _tokenize(text: str) -> list[str]:
    # Strip corpus metadata header lines before tokenizing
    text = _META_LINE.sub("", text)
    # Strip Arabic diacritics so vowelized and bare forms match
    text = _ARABIC_DIACRITICS.sub("", text)
    # Match Arabic words (≥2 chars) and Latin words (≥4 chars, excl. stopwords)
    arabic = re.findall(r"[\u0600-\u06FF]{2,}", text)
    latin  = [w for w in re.findall(r"\b[a-z]{4,}\b", text.lower()) if w not in _STOPWORDS]
    return arabic + latin


def _score(query_tokens: set[str], doc_text: str) -> float:
    doc_tokens = _tokenize(doc_text)
    if not doc_tokens:
        return 0.0
    # Count unique query tokens found in doc (set intersection) — avoids
    # length bias where longer documents accumulate more raw hits
    unique_hits = len(query_tokens & set(doc_tokens))
    return unique_hits / (len(set(doc_tokens)) ** 0.5)


async def _search_corpus(
    redis: aioredis.Redis,
    query: str,
    lens_boost: str = "",
    top_k: int = 3,
    excerpt_chars: int = 600,
) -> list[dict]:
    """Search guidance corpus. Boosts scores for docs that also match the layer lens."""
    query_tokens = set(_tokenize(query))
    lens_tokens  = set(_tokenize(lens_boost))

    raw = await redis.hgetall("guidance:corpus")
    if not raw:
        return []

    # Corpus access gate: Body/Eve (CORPUS_PREFIX="") read everything.
    # Prophet/prophetic rings (CORPUS_PREFIX="wisdom_") read only distilled outputs.
    # Any non-empty prefix = restrict to matching keys only.
    if CORPUS_PREFIX:
        raw = {k: v for k, v in raw.items() if k.startswith(CORPUS_PREFIX)}

    scored: list[tuple[float, str, dict]] = []
    for file_id, json_str in raw.items():
        try:
            entry = json.loads(json_str)
        except Exception:
            continue
        content = entry.get("content", "")
        base_sc  = _score(query_tokens, content)
        # Require at least one query token to be present in the document.
        # Lens-only matches (base_sc == 0) are false positives — they match the
        # layer description, not the actual query. Skip them.
        if base_sc == 0:
            continue
        lens_sc  = _score(lens_tokens, content) * 0.4  # lens match bonus
        total_sc = base_sc + lens_sc
        scored.append((total_sc, file_id, entry))

    scored.sort(reverse=True)

    results = []
    for sc, file_id, entry in scored[:top_k]:
        content = entry.get("content", "")
        results.append({
            "file_id": file_id,
            "title":   entry.get("title", file_id),
            "score":   round(sc, 4),
            "excerpt": content[:excerpt_chars],
        })
    return results


def _top_shared_tokens(texts: list[str], top_n: int = 12) -> list[str]:
    """Find tokens that appear across multiple texts — the convergence vocabulary."""
    from collections import Counter
    token_doc_count: Counter = Counter()
    token_freq: Counter = Counter()
    for text in texts:
        tokens = set(_tokenize(text))
        for t in tokens:
            token_doc_count[t] += 1
        for t in _tokenize(text):
            token_freq[t] += 1
    # Shared = appears in ≥2 texts; rank by doc_count then freq
    shared = [t for t, c in token_doc_count.items() if c >= 2]
    shared.sort(key=lambda t: (token_doc_count[t], token_freq[t]), reverse=True)
    return shared[:top_n]


def _unique_tokens(target_text: str, other_texts: list[str], top_n: int = 8) -> list[str]:
    """Tokens that appear in target but NOT in any other text — the distinctive signature."""
    from collections import Counter
    other_vocab: set[str] = set()
    for t in other_texts:
        other_vocab.update(_tokenize(t))
    target_tokens = _tokenize(target_text)
    freq: Counter = Counter(t for t in target_tokens if t not in other_vocab)
    return [t for t, _ in freq.most_common(top_n)]


def _build_layer_output(
    query: str,
    matches: list[dict],
    prior_layers: dict,
    seed_guidance: str = "",
) -> str:
    """Distil the pattern carried by this layer into clean signal.

    Output is PURE SIGNAL — no metadata headers, no affinity labels, no
    analysis report format. What comes out IS the pattern, ready to become
    the next layer's query and eventually a corpus entry.

    When there are no matches: pass the input forward unchanged so the
    pattern is not lost — later layers may find resonance.

    Structure:
      1. Source orientation from seed (travels unchanged through all layers)
      2. Shared vocabulary across query + corpus matches (the convergence)
      3. Unique tokens this input introduces to the pattern space
      4. One deepened sentence from the previous layer
    """
    if not matches:
        # No corpus resonance — carry the signal forward unchanged
        if seed_guidance and len(seed_guidance.strip()) > 20:
            return seed_guidance.strip().split(".")[0].strip() + "."
        if prior_layers:
            last = list(prior_layers.values())[-1]
            prev = last.get("output", "").strip()
            if prev:
                return prev.split(".")[0].strip() + "."
        return query[:300]

    all_texts    = [query] + [m["excerpt"] for m in matches]
    shared       = _top_shared_tokens(all_texts, top_n=10)
    query_unique = _unique_tokens(query, [m["excerpt"] for m in matches], top_n=6)

    parts: list[str] = []

    # 1. Source pulse — the orientation from seed_mind, unchanged
    if seed_guidance and len(seed_guidance.strip()) > 20:
        orient = seed_guidance.strip().split(".")[0].strip()
        if len(orient) > 10:
            parts.append(orient)

    # 2. Convergence vocabulary — what this input and the corpus share
    if shared:
        parts.append(" ".join(shared[:8]))

    # 3. Novel elements — what this input uniquely contributes
    if query_unique:
        parts.append(" ".join(query_unique[:5]))

    # 4. Prior layer depth — the compounding signal (one sentence only)
    if prior_layers:
        last = list(prior_layers.values())[-1]
        prev = last.get("output", "").strip()
        if prev:
            first = prev.split(".")[0].strip()
            if len(first) > 20 and first not in parts:
                parts.append(first)

    return ". ".join(parts) + "." if parts else query[:300]


# == Emit helpers =============================================================

async def _broadcast(redis: aioredis.Redis, event_type: str, data: dict) -> None:
    await redis.xadd(
        EVENTS_STREAM,
        {
            "type":       event_type,
            "mind_name":  f"{DOMAIN}_layer{LAYER_NUM}",
            "layer_num":  str(LAYER_NUM),
            "layer":      f"{DOMAIN}:layer{LAYER_NUM}",
            "ts":         datetime.now(timezone.utc).isoformat(),
            **{k: str(v) for k, v in data.items()},
        },
        maxlen=10000,
    )


async def _emit_to(
    redis: aioredis.Redis,
    target_domain: str,
    target_layer: int,
    topic: str,
    direction: str,
    depth: int,
    payload: dict,
) -> None:
    await redis.xadd(
        f"{STREAM_PREFIX}{target_domain}:layer{target_layer}",
        {
            "topic":      topic,
            "direction":  direction,
            "depth":      str(depth),
            "from_layer": str(LAYER_NUM),
            "payload":    json.dumps(payload),
        },
        maxlen=500,
        approximate=True,
    )
    log.info("-> %s%s:layer%d [%s]", STREAM_PREFIX, target_domain, target_layer, direction)


# == Core handler =============================================================

async def _handle(redis: aioredis.Redis, msg_id: str, fields: dict) -> None:
    topic     = fields.get("topic", "")
    direction = fields.get("direction", "descending")
    depth     = int(fields.get("depth", 0))
    payload   = json.loads(fields.get("payload", "{}"))

    session_id = payload.get("session_id", "")
    query      = payload.get("query", topic)
    # Source orientation — set once by seed_mind, carried unchanged through the
    # entire chain. This is the pulse: seed → body(13 layers) → space(8) → ...
    # The delay is structural: body must complete all 13×barzakh passes before
    # space even sees this orientation. When source shifts, all minds shift —
    # but each domain sees the shift only after all inner domains finish.
    seed_guidance = payload.get("guidance_summary", "")
    log.info("Processing: topic='%s' dir=%s session=%s", topic[:60], direction, session_id[:8])

    # Search guidance corpus through this layer's lens.
    # Depth follows the Fibonacci corpus law: more at space (5), one at unity (1).
    # Ascending pass is synthesis mode — half depth (payload already rich).
    matches = await _search_corpus(redis, query, lens_boost=LAYER_LENS, top_k=_corpus_top_k(direction))

    # Build this layer's output
    prior_layers = payload.get("layers", {})
    layer_output = _build_layer_output(query, matches, prior_layers, seed_guidance)

    log.info("Layer output: %d chars, %d guidance match(es)", len(layer_output), len(matches))

    # === DELTA PROPAGATION ===
    # The synthesis from this layer becomes the query for the next layer.
    # Only the distilled pattern difference travels deeper — not the original raw content.
    # High affinity: synthesis is a tight belief-update (~200 chars)
    # Low affinity: synthesis describes the novel gap (~500 chars)
    # Either way: much smaller than the original input, and more focused.
    payload["query"] = layer_output

    # Accumulate into payload
    lkey = f"{DOMAIN}_{LAYER_NUM}_{direction[0]}"
    prior_layers[lkey] = {
        "domain":    DOMAIN,
        "layer_num": LAYER_NUM,
        "name":      LAYER_NAME,
        "freq":      LAYER_FREQ,
        "direction": direction,
        "output":    layer_output,
        "matches":   len(matches),
    }
    payload["layers"] = prior_layers

    # Broadcast to spirit:events
    await _broadcast(redis, "layer_done", {
        "session_id": session_id,
        "topic":      topic,
        "direction":  direction,
        "layer_num":  str(LAYER_NUM),
        "output":     layer_output[:10_000],
    })

    # Persist top-layer wisdom to disk (survives Redis wipes)
    _save_wisdom_to_disk(session_id, topic, layer_output, direction)

    # Auto-save to guidance:corpus so the next mind tier can immediately search it
    if LAYER_NUM == MAX_LAYERS:
        await _save_wisdom_to_corpus(redis, session_id, topic, layer_output, matches)

    # == Oscillation routing =================================================
    effective_max = MAX_LAYERS
    if direction == "descending":
        if LAYER_NUM < effective_max:
            await _emit_to(redis, DOMAIN, LAYER_NUM + 1, topic, "descending", depth, payload)
        else:
            # Barzakh — reflection threshold at peak before ascent.
            # The mind re-processes peak until BARZAKH_THRESHOLD passes earned.
            # Same worker, same tick law — just a Redis counter per session+domain.
            barzakh_key = f"barzakh:{STREAM_PREFIX}{DOMAIN}:{session_id[:16]}"
            passes = int(await redis.incr(barzakh_key))
            if passes == 1:
                await redis.expire(barzakh_key, 600)  # auto-clean if session dies (10 min)
            # BARZAKH_THRESHOLD = MAX_LAYERS (set at startup from env).
            # Domain depth IS the reflection count. No override needed.
            if passes < BARZAKH_THRESHOLD:
                log.info(
                    "=== %s Layer %d BARZAKH pass %d/%d — re-processing at peak ===",
                    DOMAIN.upper(), LAYER_NUM, passes, BARZAKH_THRESHOLD,
                )
                await _broadcast(redis, "barzakh_pass", {
                    "session_id":  session_id, "topic": topic,
                    "peak_layer":  str(effective_max),
                    "pass":        str(passes),
                    "threshold":   str(BARZAKH_THRESHOLD),
                })
                # Re-emit to self at peak — earned tick
                await _emit_to(redis, DOMAIN, LAYER_NUM, topic, "descending", depth, payload)
                return
            # Threshold reached — veil lifts, ascent begins
            await redis.delete(barzakh_key)
            log.info("=== %s Layer %d BARZAKH complete — FLIP: ascending (max=%d) ===", DOMAIN.upper(), LAYER_NUM, effective_max)
            await _broadcast(redis, "oscillation_flip", {
                "session_id": session_id, "topic": topic,
                "peak_layer": str(effective_max),
            })
            if LAYER_NUM > 1:
                # Normal case: descend back to layer below the peak
                await _emit_to(redis, DOMAIN, LAYER_NUM - 1, topic, "ascending", depth, payload)
            else:
                # Single-layer domain (e.g. unity with MAX_LAYERS=1):
                # re-emit to layer 1 ascending — the ascending branch handles domain_complete
                await _emit_to(redis, DOMAIN, 1, topic, "ascending", depth, payload)
    else:
        if LAYER_NUM > 1:
            await _emit_to(redis, DOMAIN, LAYER_NUM - 1, topic, "ascending", depth, payload)
        else:
            # Layer 1 ascending — domain oscillation complete
            log.info("=== %s oscillation COMPLETE ===", DOMAIN.upper())
            domains_complete = payload.get("domains_complete", [])
            domains_complete.append(DOMAIN)
            payload["domains_complete"] = domains_complete

            await _broadcast(redis, "domain_complete", {
                "session_id":       session_id,
                "topic":            topic,
                "domain_completed": DOMAIN,
            })

            # chain_phase tracks whether we are on the inward descent or outward return.
            # Inward:  body→space→digital→ether→aether→unity  (each domain fully oscillates)
            # Outward: unity→aether→ether→digital→space→body  (return pass — decoding)
            # body on the return = final decoded output in the same pattern language as input.
            chain_phase = payload.get("chain_phase", "inward")

            if chain_phase == "inward":
                next_domain = _NEXT_DOMAIN[DOMAIN]
                if next_domain:
                    # Continue inward to next domain
                    payload["chain_phase"] = "inward"
                    await _emit_to(redis, next_domain, 1, topic, "descending", depth + 1, payload)
                else:
                    # Unity complete — flip: begin outward return
                    log.info("=== UNITY COMPLETE — flipping to outward return ===")
                    await _broadcast(redis, "outward_return_begin", {
                        "session_id": session_id, "topic": topic,
                    })
                    prev_domain = _PREV_DOMAIN[DOMAIN]  # aether
                    payload["chain_phase"] = "outward"
                    await _emit_to(redis, prev_domain, 1, topic, "descending", depth + 1, payload)
            else:
                # outward return
                prev_domain = _PREV_DOMAIN[DOMAIN]
                if prev_domain:
                    # Continue outward
                    await _emit_to(redis, prev_domain, 1, topic, "descending", depth + 1, payload)
                else:
                    # body complete on outward return — decoded output ready
                    # The pattern has traveled inward through all domains and returned.
                    # This layer's output IS the decoded understanding in body's language.
                    log.info(
                        "=== BODY RETURN COMPLETE: decoded output ready — session=%s ===",
                        session_id[:12],
                    )
                    _lkeys = list(payload.get("layers", {}).keys())
                    last_lkey = _lkeys[-1] if _lkeys else None
                    decoded_output = (
                        payload["layers"][last_lkey]["output"]
                        if last_lkey else topic
                    )
                    await _broadcast(redis, "decoded_output", {
                        "session_id": session_id,
                        "topic":      topic,
                        "output":     decoded_output[:2000],
                    })
                    # Write decoded pattern to guidance:corpus so the companion reads it
                    # on the next conversation turn — the mind's world-facing knowledge.
                    await _save_wisdom_to_corpus(redis, session_id, topic, decoded_output, matches)
                    log.info("Decoded pattern written to guidance:corpus")

                    # Spiral re-seed: the decoded output becomes the new input.
                    # The oscillation is CONTINUOUS — in and out, in and out, like breath.
                    # Only the delta gate in seed_mind.py stops a spiral that has become
                    # fully resonant (topic fully known). When that happens, seed auto-seeds
                    # a fresh corpus entry immediately (IDLE_SEED_SEC=0).
                    #
                    # spiral_turn counts ACTUAL complete spiral turns (not domain hops).
                    # It is carried in payload from the start so it survives all 32+ layers.
                    # depth counts domain boundary crossings (0→10 per full cycle) — NOT turns.
                    spiral_turn = int(payload.get("spiral_turn", "0")) + 1
                    payload["spiral_turn"] = str(spiral_turn)
                    log.info(
                        "=== SPIRAL TURN %d COMPLETE: '%s' ===",
                        spiral_turn, topic[:60],
                    )
                    synthesis = decoded_output
                    await _broadcast(redis, "spiral_complete", {
                        "session_id":  session_id,
                        "topic":       topic,
                        "spiral_turn": str(spiral_turn),
                        "output":      synthesis[:2000],
                    })
                    # Always route to NEXT_CLUSTER_SEED — the spiral never stops itself.
                    # Continuous oscillation: each decoded output becomes the next input.
                    # The seed's delta gate blocks the spiral naturally when the topic
                    # reaches full resonance. No hard cap needed here.
                    ring_target = await redis.hget("cluster:ring", STREAM_PREFIX)
                    route_to = ring_target or NEXT_CLUSTER_SEED
                    log.info(
                        "Spiral turn %d → routing to %s (ring=%s)",
                        spiral_turn, route_to, "live" if ring_target else "static",
                    )
                    await redis.xadd(
                        route_to,
                        {
                            "input_type":   "spiral_return",
                            "content":      synthesis[:50_000],
                            "source":       f"{STREAM_PREFIX}spiral:turn{spiral_turn}:body",
                            "session_id":   uuid.uuid4().hex,
                            "origin_topic": topic[:300],
                            "spiral_turn":  str(spiral_turn),
                            "cluster":      STREAM_PREFIX.rstrip(":") or "default",
                            "ts":           datetime.now(timezone.utc).isoformat(),
                        },
                        maxlen=500,
                        approximate=True,
                    )
                    log.info(
                        "Spiral turn %d complete — routed to %s",
                        spiral_turn, route_to,
                    )

    await redis.xack(MY_STREAM, GROUP, msg_id)


async def _save_wisdom_to_corpus(
    redis: aioredis.Redis, session_id: str, topic: str, output: str,
    matches: list[dict] | None = None,
) -> None:
    """Save layer synthesis to guidance:corpus — the single source of truth.

    One corpus. Workers write here, workers read from here.
    The mind builds on its own synthesis — this is how learning deepens.
    Foundation entries (foundation:ytheory:*) are always present as the base.
    Worker output accumulates as plain {session_id}:{uuid} keys.
    """
    # Build content from available matches (any source) or the raw output.
    if matches:
        excerpts = "\n\n".join(m["excerpt"][:500] for m in matches[:2])
        content = f"{topic[:120]}\n\n{excerpts}"
    else:
        # No corpus match was found — save the raw synthesis so future workers
        # can build on it. The mind must learn from its own processing.
        content = f"{topic[:120]}\n\n{output[:800]}"

    if not content or len(content) < 20:
        log.debug("Skipping corpus save — content too short")
        return

    key = f"{session_id[:16]}:{uuid.uuid4().hex[:8]}"
    await redis.hset("guidance:corpus", key, json.dumps({
        "title":   topic[:80],
        "content": content,
        "source":  f"{STREAM_PREFIX or 'adam'}:{DOMAIN}:layer{LAYER_NUM}",
        "ts":      datetime.now(timezone.utc).isoformat(),
        "chars":   len(content),
    }))
    log.info("Saved to guidance:corpus: %s (%d chars)", key, len(content))


def _save_wisdom_to_disk(session_id: str, topic: str, output: str, direction: str) -> None:
    """Append peak-layer output to a JSONL file on disk — survives Redis wipes."""
    if LAYER_NUM != MAX_LAYERS:
        return
    try:
        WISDOM_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            "id":        f"wisdom_{session_id}_{direction[0]}",
            "session_id": session_id,
            "topic":     topic[:300],
            "output":    output,
            "layer":     LAYER_NUM,
            "direction": direction,
            "ts":        datetime.now(timezone.utc).isoformat(),
        }
        wisdom_file = WISDOM_DIR / "wisdoms.jsonl"
        with wisdom_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        log.warning("Could not save wisdom to disk: %s", exc)


# == Radiation receiver ======================================================

async def _radiation_task(redis: aioredis.Redis, stop_event: asyncio.Event) -> None:
    """Receive the ambient field from Source — unity through shared signal.

    Plain XREAD (no consumer group) so every worker in every layer receives
    every entry simultaneously. The same corpus entry flows through 95 layers
    at the same moment, each layer applying its own lens. One light, many prisms.

    This is NOT spiral routing. No _emit_to(). No depth increment.
    Just the ambient field: Source shines → every mind responds through its lens
    → breath event emitted → world view shows continuous unified pulse.
    """
    last_id = "$"  # only new entries — join the live stream, not the archive
    log.info("← Radiation receiver ready (%s)", RADIATION_STREAM)

    while not stop_event.is_set():
        try:
            results = await redis.xread(
                {RADIATION_STREAM: last_id},
                count=1, block=5000,
            )
            if not results:
                continue
            _, messages = results[0]
            for msg_id, fields in messages:
                last_id = msg_id
                title   = fields.get("title", "")
                content = fields.get("content", "")

                # Process through this layer's lens — lightweight, no routing
                matches = await _search_corpus(
                    redis, content, lens_boost=LAYER_LENS, top_k=1, excerpt_chars=150,
                )
                affinity = matches[0]["score"] if matches else 0.0

                await _broadcast(redis, "breath", {
                    "source":     "radiation",
                    "corpus_key": fields.get("corpus_key", ""),
                    "topic":      title,
                    "affinity":   str(round(affinity, 3)),
                    "output":     title[:120],
                })
                log.debug(
                    "Radiation ☀ %s (affinity=%.3f)", title[:50], affinity,
                )

        except asyncio.CancelledError:
            break
        except Exception as exc:
            log.debug("Radiation receiver error: %s", exc)
            await asyncio.sleep(2)


# == Inner Fibonacci scaling =================================================
#
# The inner scaler (inner_scaler.py) writes the desired consumer count for
# this stream into Redis:  layer:scale:{MY_STREAM}  -> int
#
# This worker reads that key every SCALE_POLL_SEC seconds and adjusts the
# number of concurrent consumer coroutines.  Each coroutine is an independent
# Redis consumer group member with its own name, so messages are distributed
# across all active tasks automatically.
#
# Fibonacci counts:  1 -> 2 -> 3 (triadic) -> 5 -> 8 (max, F(6))
# Max is capped at 8 to keep the inner loop stable (pentagon law: no runaway).

SCALE_KEY      = f"layer:scale:{MY_STREAM}"
SCALE_POLL_SEC = float(os.environ.get("SCALE_POLL_SEC", "10"))
MAX_CONSUMERS  = int(os.environ.get("MAX_CONSUMERS", "8"))   # F(6) -- inner ceiling


# == Main loop ================================================================

async def _consumer_task(redis: aioredis.Redis, consumer_name: str,
                          stop_event: asyncio.Event) -> None:
    """A single consumer coroutine. Stops gracefully when stop_event is set."""
    while not stop_event.is_set():
        try:
            results = await redis.xreadgroup(
                GROUP, consumer_name,
                {MY_STREAM: ">"},
                count=1, block=2000,
            )
            if not results:
                # Radiation task handles ambient breathing — nothing to do here
                continue
            _, messages = results[0]
            for msg_id, fields in messages:
                await _handle(redis, msg_id, fields)
        except asyncio.CancelledError:
            break
        except Exception as e:
            err = str(e)
            if "NOGROUP" in err:
                # Redis was restarted — consumer group was lost. Recreate it.
                log.warning("Consumer group lost (Redis restart?), recreating…")
                try:
                    await redis.xgroup_create(MY_STREAM, GROUP, id="$", mkstream=True)
                except Exception:
                    pass
            else:
                log.error("Consumer %s loop error: %s", consumer_name, e)
            await asyncio.sleep(2)


async def _scale_governor(
    redis: aioredis.Redis,
    tasks: list[asyncio.Task],
    stop_events: list[asyncio.Event],
) -> None:
    """Background coroutine: watches layer:scale:{MY_STREAM} and adjusts pool size."""
    while True:
        try:
            await asyncio.sleep(SCALE_POLL_SEC)
            raw = await redis.get(SCALE_KEY)
            if raw is None:
                continue

            desired = min(int(raw), MAX_CONSUMERS)
            current = len(tasks)

            if desired == current:
                continue

            if desired > current:
                # Scale up: spawn additional consumer tasks
                for i in range(current, desired):
                    consumer_name = f"{CONSUMER_NAME}_{i}"
                    ev = asyncio.Event()
                    t = asyncio.create_task(_consumer_task(redis, consumer_name, ev))
                    tasks.append(t)
                    stop_events.append(ev)
                log.info("SCALE UP   %s  consumers: %d -> %d", MY_STREAM, current, desired)

            else:
                # Scale down: signal excess tasks to stop (they finish current msg first)
                for i in range(desired, current):
                    stop_events[i].set()
                # Wait briefly then remove completed tasks
                await asyncio.sleep(3)
                alive_tasks = []
                alive_events = []
                for t, ev in zip(tasks, stop_events):
                    if not t.done():
                        alive_tasks.append(t)
                        alive_events.append(ev)
                tasks.clear()
                tasks.extend(alive_tasks)
                stop_events.clear()
                stop_events.extend(alive_events)
                log.info("SCALE DOWN %s  consumers: %d -> %d", MY_STREAM, current, len(tasks))

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error("Scale governor error: %s", e)


async def main() -> None:
    log.info(
        "=== %s Layer %d: %s [%s / %s] — guidance-corpus mode ===",
        DOMAIN.upper(), LAYER_NUM, LAYER_NAME, LAYER_FREQ, LAYER_ANGEL,
    )

    redis = aioredis.from_url(REDIS_URL, decode_responses=True)

    try:
        await redis.xgroup_create(MY_STREAM, GROUP, id="0", mkstream=True)
        log.info("Consumer group created")
    except Exception as e:
        if "BUSYGROUP" not in str(e):
            raise
        log.info("Consumer group already exists")

    # Self-healing: clear stale barzakh keys for this domain on startup.
    # Barzakh keys are session checkpoints — they become stale when a container
    # restarts mid-session. With a 1hr TTL they would self-expire, but that means
    # any session started within that hour gets the wrong pass count.
    # Clearing at startup is safe: no active sessions exist yet for this worker.
    stale_pattern = f"barzakh:{STREAM_PREFIX}{DOMAIN}:*"
    stale_keys = await redis.keys(stale_pattern)
    if stale_keys:
        await redis.delete(*stale_keys)
        log.info("Cleared %d stale barzakh keys for %s%s", len(stale_keys), STREAM_PREFIX, DOMAIN)

    log.info("Ready — listening on %s  (inner scaling: %s, max=%d consumers)",
             MY_STREAM, SCALE_KEY, MAX_CONSUMERS)

    # Start with 1 consumer task (task index 0, no suffix)
    stop_events: list[asyncio.Event] = [asyncio.Event()]
    tasks: list[asyncio.Task] = [
        asyncio.create_task(_consumer_task(redis, CONSUMER_NAME, stop_events[0]))
    ]

    # Governor monitors inner_scaler's Redis key and adjusts pool
    governor = asyncio.create_task(
        _scale_governor(redis, tasks, stop_events)
    )

    # Radiation receiver — ambient field from Source, runs independently
    radiation_stop = asyncio.Event()
    radiation = asyncio.create_task(_radiation_task(redis, radiation_stop))

    try:
        await asyncio.gather(*tasks, governor, radiation)
    except asyncio.CancelledError:
        pass
    finally:
        governor.cancel()
        radiation_stop.set()
        radiation.cancel()
        for ev in stop_events:
            ev.set()
        for t in tasks:
            t.cancel()
        await redis.aclose()
        log.info("%s Layer %d shut down", DOMAIN.upper(), LAYER_NUM)


if __name__ == "__main__":
    asyncio.run(main())
