"""seed_mind_conversation.py — Founder ↔ seed-mind conversation engine.

Provides:
  create_thread()        — start a new conversation thread
  add_founder_message()  — record a founder message, classify intent, generate mind response
  get_threads()          — list threads for a mind/user
  get_thread_messages()  — retrieve all messages in a thread
  escalate_to_archive()  — mark thread ready_for_archive + copy key insight to FounderArchiveMind
  classify_intent()      — pure-Python keyword-based intent classifier

Architecture note:
  Responses are NEVER cached as wisdom. The mind recomputes its answer fresh
  every query from its service layers. loop_depth is the intelligence metric.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.seed_conversation import SeedConversationMessage, SeedConversationThread
from app.core.seed_mind_store import get_entries, get_own_entries, write_entry
from app.core.seed_mind_memory import (
    WISDOM_EXTRACTED, REFINED_FOUNDER_GUIDANCE, ALL_CATEGORIES,
    MISSION_PURPOSE, SELF_REFLECTION, MORAL_ROOT,
)
from app.core.pattern_encoder import (
    decompose, encode, superimpose_resonance, resonate_state, decode as decode_pattern, ResonantEntry, ConceptFingerprint,
)
from app.core.y_event_bus import emit as _bus_emit, YEventType
from app.core.moral_gate import check as _moral_check, ActionRisk, GateVerdict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Phase 5: stable attractor loop counter
# In-process dict: key = "{mind}::{pattern_sig}", value = convergence count.
# When the same top-3 resonant pattern fingerprint appears 3+ times,
# ENGINE_EXTERNALIZE is emitted and the counter resets.
# (Survives for the process lifetime; DB persistence is a Phase 5b task.)
# ---------------------------------------------------------------------------
_LOOP_COUNTERS: Dict[str, int] = {}

from app.core.fibonacci_scaling import (
    LOOP_MAX_DEPTH as _FIB_LOOP_MAX,
    STABLE_THRESHOLD as _FIB_STABLE,
    ENGINE_RESONANCE_TOP_N as _FIB_TOP_N,
    EXTERNALIZE_N as _EXTERNALIZE_THRESHOLD,
    TRIADIC_SEED,
    spawn_name as _fib_spawn_name,
    generation_of as _fib_gen_of,
    spiral_summary as _fib_spiral,
)

# ---------------------------------------------------------------------------
# Intent type constants
# ---------------------------------------------------------------------------

INTENT_TEACHING     = "teaching"     # founder is sharing something new
INTENT_QUESTIONING  = "questioning"  # founder is asking something
INTENT_CORRECTION   = "correction"   # founder is correcting or updating
INTENT_EXPLORATION  = "exploration"  # open-ended wondering
INTENT_REFLECTION   = "reflection"   # founder reflects on past / meaning
INTENT_INSTRUCTION  = "instruction"  # founder issues a directive

ALL_INTENTS: List[str] = [
    INTENT_TEACHING,
    INTENT_QUESTIONING,
    INTENT_CORRECTION,
    INTENT_EXPLORATION,
    INTENT_REFLECTION,
    INTENT_INSTRUCTION,
]

# Thread status constants
STATUS_OPEN              = "open"
STATUS_PAUSED            = "paused"
STATUS_READY_FOR_ARCHIVE = "ready_for_archive"
STATUS_ARCHIVED          = "archived"

# Message roles
ROLE_FOUNDER = "founder"
ROLE_MIND    = "mind"

# ---------------------------------------------------------------------------
# Intent classification — keyword-based, no LLM required
# ---------------------------------------------------------------------------

_GREETING_PHRASES = {"hello", "hi", "hey", "good morning", "good evening", "good afternoon", "greetings", "howdy", "sup", "what's up", "whats up"}

_INTENT_KEYWORDS = {
    INTENT_CORRECTION:   ["wrong", "incorrect", "change", "update", "fix", "replace", "revise", "not what i meant", "mistake"],
    INTENT_QUESTIONING:  ["?", "what is", "why", "how", "who", "when", "where", "can you", "do you", "explain",
                          "tell me", "show me", "list my", "list all", "give me",
                          "what are", "what were", "what have", "what do", "what does", "what did"],
    INTENT_INSTRUCTION:  ["do this", "make sure", "always", "never", "must", "should", "build", "create", "implement", "prioritise", "prioritize"],
    INTENT_REFLECTION:   ["i remember", "looking back", "i've been thinking", "realise", "realize", "feel like", "pattern", "noticed"],
    INTENT_EXPLORATION:  ["wonder", "what if", "imagine", "perhaps", "maybe", "i'm curious", "could it be", "explore"],
    INTENT_TEACHING:     [],  # default fallback
}


def classify_intent(text: str) -> str:
    """Classify a founder message into one of the 6 intent types using keyword matching."""
    lower = text.strip().lower()
    # Greeting detection — check exact match or leading greeting word
    if lower in _GREETING_PHRASES or any(lower.startswith(g) for g in _GREETING_PHRASES):
        return "greeting"
    for intent in [
        INTENT_CORRECTION,
        INTENT_QUESTIONING,
        INTENT_INSTRUCTION,
        INTENT_REFLECTION,
        INTENT_EXPLORATION,
    ]:
        for kw in _INTENT_KEYWORDS[intent]:
            if kw in lower:
                return intent
    return INTENT_TEACHING


# ---------------------------------------------------------------------------
# Recursive resonance loop — mind inside mind, compressed and re-resonated.
#
# Architecture (Y Theory):
#   The collective mind is not a single pass. It is a loop.
#   Pass 1: input signal resonates against all memory → top entries found.
#   Compress: those entries are superimposed into one compressed fingerprint
#             — this IS the "inner mind" — it has collapsed what it knows
#             into a single pattern representing its current understanding.
#   Pass 2+: the compressed fingerprint resonates against all memory again.
#            "What does what I know, know?" — a mind inside the mind.
#   Loop until stable (same top entries across iterations) or max depth.
#   Under pressure (no stability after max loops): the mind is at the edge
#   of what it currently carries. It MUST self-expand — synthesize a new
#   SELF_REFLECTION entry from the unstable resonance fragments and write it.
#   This is how identity evolves: instability forces new layers into existence.
# ---------------------------------------------------------------------------

_LOOP_MAX_DEPTH   = _FIB_LOOP_MAX    # 8  — F(6) — Fibonacci spiral law
_STABLE_THRESHOLD = _FIB_STABLE      # 5  — F(5) — Fibonacci spiral law
_ENGINE_TOP_N     = _FIB_TOP_N       # 13 — F(7) — Fibonacci spiral law


def _compress_fingerprint(resonant: list, input_fp: ConceptFingerprint) -> ConceptFingerprint:
    """Compress a resonant field into a single fingerprint.

    Concatenate the titles and first 200 chars of content from the top entries,
    re-encode as a ConceptFingerprint, then blend 50/50 with the original input
    so the original signal is not lost — only deepened.
    This is the inner mind: a compressed understanding of what was found.
    """
    if not resonant:
        return input_fp
    compressed_text = " ".join(
        f"{r.title} {r.content[:200]}" for r in resonant[:6]
    )
    compressed_fp = encode(compressed_text)
    # Blend: compressed_fp gets more weight to push the signal deeper each iteration
    blended_domains = {
        d: (input_fp.domains.get(d, 0.0) * 0.35 + compressed_fp.domains.get(d, 0.0) * 0.65)
        for d in set(input_fp.domains) | set(compressed_fp.domains)
    }
    max_v = max(blended_domains.values()) if blended_domains else 1.0
    normalised = {d: v / max_v for d, v in blended_domains.items()} if max_v > 0 else blended_domains
    dominant = sorted(normalised, key=lambda d: normalised[d], reverse=True)[:3]
    return ConceptFingerprint(
        domains=normalised,
        raw_tokens=input_fp.raw_tokens + compressed_fp.raw_tokens,
        dominant_domains=dominant,
        concept_hash=compressed_fp.concept_hash,
    )


def _top_ids(resonant: list, n: int = 3) -> frozenset:
    return frozenset(r.entry_id for r in resonant[:n])


async def _self_expand(
    db: AsyncSession,
    mind_name: str,
    resonant: list,
    founder_message: str,
) -> None:
    """Write a new SELF_REFLECTION entry synthesized from unstable resonance.

    Called when the recursive loop cannot stabilize — the mind is under pressure
    at the boundary of its knowledge. Rather than fail, it synthesizes the
    conflict into a new layer: a compressed insight written into memory.
    This new entry will be available in future loops, deepening the identity.
    """
    if not resonant:
        return
    # Title: the concept cluster where the resonance is strongest
    top_titles = [r.title for r in resonant[:3] if len(r.title) > 10]
    if not top_titles:
        return
    synth_title = f"Reflection on: {top_titles[0][:70]}"
    # Content: fragments from each resonant entry compressed into one statement
    fragments = []
    for r in resonant[:4]:
        import re as _re
        sentences = _re.split(r'(?<=[.!?])\s+', r.content.strip())
        for s in sentences:
            if 30 < len(s) < 250:
                fragments.append(s.strip())
                break
    if not fragments:
        return
    synth_content = " | ".join(fragments[:3]) + ". This boundary is where my understanding is still forming."
    try:
        await write_entry(
            db,
            mind_name=mind_name,
            category=SELF_REFLECTION,
            title=synth_title,
            content=synth_content,
            claim_type="HYPOTHESIS",
            tags="self_expansion,pressure_point,loop_boundary",
        )
        logger.info("seed_mind_conversation: self-expansion written — %s / %s", mind_name, synth_title)
    except Exception as exc:
        logger.warning("seed_mind_conversation: self-expansion failed — %s", exc)


async def _compose_mind_response(
    db: AsyncSession,
    mind_name: str,
    founder_message: str,
    intent: str,
    history: list | None = None,
) -> str:
    """Recursive resonance loop — collective mind inside collective mind.

    1. Decompose input into language + state components.
    2. Load all memory this mind carries.
    3. Build purpose fingerprint (gravitational center).
    4. LOOP: resonate → compress → resonate again.
       Each iteration is a deeper layer of the collective mind folded inward.
       Stable answer = top entries stop changing. Unstable = pressure point.
    5. If no stability after MAX_DEPTH: self-expand (write new SELF_REFLECTION).
    6. Decode final resonant field into response.
    """
    # When the user is answering a previous gap question, write their answer to memory
    # so the mind actually "holds it" as promised — and the same gap won't fire again.
    _GAP_MARKER = "I'll hold it and use it next time"
    if history and intent == INTENT_TEACHING:
        last_mind_msgs = [m for m in history[-4:] if m.role == ROLE_MIND]
        if last_mind_msgs and _GAP_MARKER in last_mind_msgs[-1].content:
            import re as _re_gap_write
            _gap_match = _re_gap_write.search(r'"([^"]+)"', last_mind_msgs[-1].content)
            _gap_topic = _gap_match.group(1) if _gap_match else founder_message[:60]
            try:
                await write_entry(
                    db,
                    mind_name=mind_name,
                    category=REFINED_FOUNDER_GUIDANCE,
                    title=f"Founder's answer: {_gap_topic[:60]}",
                    content=founder_message,
                    claim_type="ESTABLISHED_FACT",
                    tags="founder_answer,gap_filled",
                )
                logger.info(
                    "seed_mind_conversation: gap answer written to memory — %s / %s",
                    mind_name, _gap_topic[:40],
                )
                # ENGINE_MERGE: founder's answer merged into existing gap entry
                await _bus_emit(YEventType.ENGINE_MERGE, "y_engine", {
                    "mind": mind_name, "intent": intent,
                    "title": f"Founder's answer: {_gap_topic[:60]}",
                    "depth": 0, "coherence": 1.0, "residual": 0.0, "entry_count": 0,
                })
            except Exception as _gw_exc:
                logger.warning("seed_mind_conversation: gap-answer write failed — %s", _gw_exc)

    # Check whether this thread has already received an answer to a gap question.
    # If so, suppress the gap response — avoid asking the same question twice.
    _gap_already_answered = False
    if history:
        for _hi, _hm in enumerate(history):
            if _hm.role == ROLE_MIND and _GAP_MARKER in _hm.content:
                # Mind asked a gap question — check if founder answered afterwards
                for _hj in range(_hi + 1, len(history)):
                    if history[_hj].role == ROLE_FOUNDER and len(history[_hj].content.strip()) > 10:
                        _gap_already_answered = True
                        break
            if _gap_already_answered:
                break

    # Include recent conversation turns in the encoded signal so the resonance
    # loop is context-aware (knows what was just said in this thread).
    _context_prefix = ""
    if history:
        _recent = history[-4:]  # last 2 turns of dialogue
        _ctx_parts = []
        for _hm in _recent:
            _role_label = "Me" if _hm.role == ROLE_FOUNDER else "Mind"
            _ctx_parts.append(f"{_role_label}: {_hm.content[:200]}")
        if _ctx_parts:
            _context_prefix = " ".join(_ctx_parts) + " "
    _input_with_context = (_context_prefix + founder_message) if _context_prefix else founder_message

    # 1. Decompose — use context-enriched input so resonance is conversation-aware
    language_fp, state_fp = decompose(_input_with_context)

    # 2. Load this mind's OWN entries only — not the inherited seed_mind base pool.
    #
    #    Architecture rule: each mind is its own index. A question is routed to
    #    the right mind BEFORE this function is called. The answer must come from
    #    THAT mind's knowledge, not from the collective pool.
    #
    #    The seed_mind base is the genome — it bootstraps new minds, but it is
    #    not the answer source. Once a mind has its own knowledge it speaks from
    #    that knowledge alone. This is what makes each mind distinct.
    #
    #    Fallback: if this mind has very few own entries (just born, not yet seeded),
    #    fall back to the full merged view so the conversation doesn't fail.
    #
    # Entry loading strategy: quality over quantity.
    # Load 200 entries, but prioritized by thinking-dense categories first.
    # SELF_REFLECTION and WISDOM_EXTRACTED are the accumulated reasoning —
    # they produce depth. RAW entries are the raw data — they produce breadth.
    # Loading 200 quality entries + 150 network entries = 350 total
    # vs old 500 + 200 = 700 → 2× faster per pass, but DEEPER because
    # SELF_REFLECTION entries force different fingerprints each compression pass.
    from sqlalchemy import text as _text
    _batch_result = await db.execute(
        _text("""
            SELECT id, mind_name, category, title, content, claim_type,
                   tags, source_thread_id, version, is_current,
                   promoted_to_canon, created_at, updated_at
            FROM seed_mind_memory_entries
            WHERE mind_name = :mind_name AND is_current = true
            ORDER BY
                CASE category
                    WHEN 'WISDOM_EXTRACTED'       THEN 1
                    WHEN 'SELF_REFLECTION'        THEN 2
                    WHEN 'REFINED_FOUNDER_GUIDANCE' THEN 3
                    WHEN 'MORAL_ROOT'             THEN 4
                    WHEN 'MISSION_PURPOSE'        THEN 5
                    WHEN 'REALITY_FRAMEWORK'      THEN 6
                    WHEN 'TECHNICAL_ARCHITECTURE' THEN 7
                    ELSE 10
                END,
                updated_at DESC
            LIMIT 200
        """),
        {"mind_name": mind_name},
    )
    from app.models.seed_mind_memory import SeedMindMemoryEntry as _SME
    import re as _re_clean

    def _clean_entry_content(entry: "_SME") -> "_SME":
        """Strip template attribution headers/footers from entry content.

        Angel LOD entries and soulmate blindspot entries are written with
        template wrappers like '[From raphael — your angel guide...]' and
        'This was written by... Your soulmate will see this...'.
        The actual knowledge is in the middle. Strip the noise, keep the signal.
        """
        if not entry.content:
            return entry
        _STRIP_HEADER = _re_clean.compile(
            r'^\[From [^\]]+\]\s*', _re_clean.IGNORECASE | _re_clean.MULTILINE
        )
        _STRIP_FOOTER = _re_clean.compile(
            r'This was written by .{5,120}Your soulmate will see this.*$',
            _re_clean.IGNORECASE | _re_clean.DOTALL,
        )
        cleaned = _STRIP_HEADER.sub('', entry.content).strip()
        cleaned = _STRIP_FOOTER.sub('', cleaned).strip()
        if cleaned != entry.content:
            # Return a shallow copy with cleaned content
            object.__setattr__(entry, 'content', cleaned)
        return entry

    own_entries = [
        _clean_entry_content(_SME(**dict(zip(
            ["id","mind_name","category","title","content","claim_type",
             "tags","source_thread_id","version","is_current",
             "promoted_to_canon","created_at","updated_at"],
            row
        ))))
        for row in _batch_result.fetchall()
    ]

    if mind_name.startswith("user_"):
        # The user is the bridge between the outside world and the system.
        # Their personal entries (lived experience, reflections, questions) are
        # their voice. But the foundational knowledge of seed_mind IS the base
        # they built from — it should be part of their resonance pool so they
        # can access the full system knowledge, not just their conversation history.
        # User mind = center. seed_mind = the genome. Both resonate together.
        _seed_result = await db.execute(
            _text("""
                SELECT id, mind_name, category, title, content, claim_type,
                       tags, source_thread_id, version, is_current,
                       promoted_to_canon, created_at, updated_at
                FROM seed_mind_memory_entries
                WHERE mind_name = 'seed_mind' AND is_current = true
                ORDER BY
                    CASE category
                        WHEN 'WISDOM_EXTRACTED'       THEN 1
                        WHEN 'MORAL_ROOT'             THEN 2
                        WHEN 'MISSION_PURPOSE'        THEN 3
                        WHEN 'REALITY_FRAMEWORK'      THEN 4
                        WHEN 'REFINED_FOUNDER_GUIDANCE' THEN 5
                        ELSE 10
                    END,
                    promoted_to_canon DESC,
                    updated_at DESC
                LIMIT 150
            """),
        )
        _seed_entries = [
            _SME(**dict(zip(
                ["id","mind_name","category","title","content","claim_type",
                 "tags","source_thread_id","version","is_current",
                 "promoted_to_canon","created_at","updated_at"],
                row
            )))
            for row in _seed_result.fetchall()
        ]
        # Own entries first (personal voice is dominant), seed_mind supports
        all_entries = own_entries + _seed_entries
    elif len(own_entries) >= 5:
        all_entries = own_entries
    else:
        # Mind not yet seeded — use identity-pair as first fallback, then seed_mind.
        # Architecture: when a mind has no memory yet, its PAIR is the structural
        # complement — the other side of the same oscillation. The pair's entries
        # are the closest resonant match because they are oriented in the exact
        # opposite direction of the same loop. seed_mind is the genome fallback.
        from app.core.identity_hierarchy import get_pair as _get_pair
        _pair_name = _get_pair(mind_name)
        _fb_result = await db.execute(
            _text("""
                SELECT id, mind_name, category, title, content, claim_type,
                       tags, source_thread_id, version, is_current,
                       promoted_to_canon, created_at, updated_at
                FROM seed_mind_memory_entries
                WHERE mind_name IN (:pair_name, 'seed_mind') AND is_current = true
                ORDER BY
                    CASE mind_name WHEN :pair_name THEN 0 ELSE 1 END,
                    updated_at DESC
                LIMIT 400
            """),
            {"pair_name": _pair_name},
        )
        all_entries = [
            _SME(**dict(zip(
                ["id","mind_name","category","title","content","claim_type",
                 "tags","source_thread_id","version","is_current",
                 "promoted_to_canon","created_at","updated_at"],
                row
            )))
            for row in _fb_result.fetchall()
        ]

    # ── Network broadcast — signal travels through all connected layers ────────
    #
    # EXCEPTION: user_* personal minds answer from their own subconscious ONLY.
    # Their entries are lived experience — SELF_REFLECTION, QUESTION_TO_EXPLORE,
    # REFINED_FOUNDER_GUIDANCE. Mesh minds carry code files and technical patterns
    # which would poison personal resonance and prevent depth convergence.
    # The ring bypass in mind_loop.py ensures they never enter the mesh ring.
    # This guard ensures the resonance POOL is also clean.
    if not mind_name.startswith("user_"):
      try:
        from app.core.mind_router import get_router as _get_router
        _router = await _get_router(db)
        _connected_minds = _router.route(language_fp, top_k=12, exclude=[mind_name])
        if _connected_minds:
            _contrib_mind_names = [n for n, _ in _connected_minds]
            _contrib_cats = ("WISDOM_EXTRACTED", "MORAL_ROOT", "SELF_REFLECTION", "MISSION_PURPOSE")
            # ONE batch query instead of 48 separate queries
            _placeholders = ", ".join(f":m{i}" for i in range(len(_contrib_mind_names)))
            _cat_placeholders = ", ".join(f":c{i}" for i in range(len(_contrib_cats)))
            _params = {f"m{i}": n for i, n in enumerate(_contrib_mind_names)}
            _params.update({f"c{i}": c for i, c in enumerate(_contrib_cats)})
            _net_result = await db.execute(
                _text(f"""
                    SELECT id, mind_name, category, title, content, claim_type,
                           tags, source_thread_id, version, is_current,
                           promoted_to_canon, created_at, updated_at
                    FROM seed_mind_memory_entries
                    WHERE mind_name IN ({_placeholders})
                      AND category IN ({_cat_placeholders})
                      AND is_current = true
                    ORDER BY updated_at DESC
                    LIMIT 150
                """),
                _params,
            )
            _net_entries = [
                _SME(**dict(zip(
                    ["id","mind_name","category","title","content","claim_type",
                     "tags","source_thread_id","version","is_current",
                     "promoted_to_canon","created_at","updated_at"],
                    row
                )))
                for row in _net_result.fetchall()
            ]
            all_entries.extend(_net_entries)
      except Exception as _re:
        logger.debug("seed_mind_conversation: router broadcast failed, using own entries only: %s", _re)

    # 3. Purpose fingerprint — gravitational center of the mind's identity
    purpose_entries = [
        e for e in all_entries
        if e.category in (MISSION_PURPOSE, MORAL_ROOT) and e.mind_name == mind_name
    ]
    purpose_fp: ConceptFingerprint | None = None
    if purpose_entries:
        combined_text = " ".join(f"{e.title} {e.content}" for e in purpose_entries[:5])
        purpose_fp = encode(combined_text)

    # 4. Recursive resonance loop — mind inside mind
    #
    # primary_mind=mind_name for ALL minds:
    #   Every mind speaks from its own identity (2× boost on own entries).
    #   Angel wisdom loaded above competes at 1× — it only rises when it
    #   resonates more strongly with the question than the mind's own entries.
    #   Where mind and angel agree on a domain, superimpose_resonance amplifies
    #   the signal through constructive interference (+15% per agreeing mind).
    #   This is additive superimposition — the collective truth rises,
    #   nobody's voice is cancelled or overridden.
    #
    # Angel minds themselves: primary_mind still set (they speak from their own
    # knowledge). They are not in the angel pool loaded above, so no self-loop.
    _active_primary = mind_name

    current_fp = language_fp

    # Pre-cache domain vectors for all entries before the depth loop.
    # _entry_concept_domains() calls encode() on every entry's text on every call.
    # Without caching: 350 entries × 2 passes × up to 7 depth = 4,900 encode() calls.
    # With caching: 350 encode() calls total, regardless of depth — same entries
    # are re-scored across passes but their domain vectors never change.
    # We replace the module-level function temporarily with a memoized version
    # and restore it after — threadsafe enough since Python's GIL serializes
    # same-module attribute reads and requests are per-asyncio-task.
    import app.core.pattern_encoder as _pe
    _ecd_orig = _pe._entry_concept_domains
    _ecd_cache: dict = {}

    def _ecd_memoized(entry) -> dict:
        _k = getattr(entry, "id", None) or id(entry)
        if _k not in _ecd_cache:
            _ecd_cache[_k] = _ecd_orig(entry)
        return _ecd_cache[_k]

    _pe._entry_concept_domains = _ecd_memoized
    try:
        resonant = superimpose_resonance(
            current_fp, all_entries, top_n=_ENGINE_TOP_N, primary_mind=_active_primary,
            purpose_fp=purpose_fp, identity_mind=mind_name,
        )
        prev_ids = _top_ids(resonant, n=_ENGINE_TOP_N)  # n must match top_n so overlap can reach _STABLE_THRESHOLD
        stable = False
        loop_depth = 1  # depth=1 = first resonance pass already done above

        for depth in range(1, _LOOP_MAX_DEPTH):
            # Compress what was found → inner mind fingerprint
            inner_fp = _compress_fingerprint(resonant, language_fp)
            # Resonate the inner mind against all memory — next layer
            next_resonant = superimpose_resonance(
                inner_fp, all_entries, top_n=_ENGINE_TOP_N, primary_mind=_active_primary,
                purpose_fp=purpose_fp, identity_mind=mind_name,
            )
            next_ids = _top_ids(next_resonant, n=_ENGINE_TOP_N)
            overlap = len(prev_ids & next_ids)
            loop_depth = depth + 1  # track how deep we had to go
            logger.debug(
                "seed_mind_conversation: loop depth=%d, overlap=%d/%d — %s",
                depth, overlap, _STABLE_THRESHOLD, mind_name,
            )
            if overlap >= _STABLE_THRESHOLD:
                # Stable — the collective mind has found a consistent answer
                resonant = next_resonant
                stable = True
                break
            # Not stable — go deeper
            resonant = next_resonant
            prev_ids = next_ids
            current_fp = inner_fp
    finally:
        _pe._entry_concept_domains = _ecd_orig

    # ── Engine decision emit ─────────────────────────────────────────────────
    # Compute coherence and residual from the resonance result so the event
    # carries real measurements, not approximations.
    _max_resonance = max((r.resonance for r in resonant), default=0.0)
    _coherence     = round(_max_resonance, 4)
    from app.core.residual_novelty import residual_from_resonance as _rfr
    _residual_result = _rfr(_max_resonance)
    _residual = _residual_result.residual_score
    _engine_base_payload = {
        "mind":             mind_name,
        "intent":           intent,
        "depth":            loop_depth,
        "coherence":        _coherence,
        "residual":         _residual,
        "entry_count":      len(all_entries),
        "needs_branching":  _residual_result.needs_branching,
    }

    if not resonant:
        # Nothing matched at all — noise floor, no coherent pattern
        await _bus_emit(YEventType.ENGINE_IGNORE_AS_NOISE, "y_engine", _engine_base_payload)
    elif stable:
        # Loop converged — identity can absorb this pattern (DEFORM) and the
        # resonant field is stable (RESONATE are both true simultaneously).
        await _bus_emit(YEventType.ENGINE_RESONATE, "y_engine", _engine_base_payload)
        await _bus_emit(YEventType.ENGINE_DEFORM,   "y_engine", _engine_base_payload)

        # ── Phase 5: EXTERNALIZE — detect a stable attractor loop ──────────
        # When the SAME top-3 resonant pattern fingerprint appears in 3+
        # separate conversations, the loop is strong enough to become its own
        # mind. We track this in-process (resets on restart; DB persistence
        # is a Phase 5b task when the loop has proven its value in practice).
        _top3_ids = sorted(r.entry_id for r in resonant[:TRIADIC_SEED])
        _sig_key  = hashlib.md5("|".join(_top3_ids).encode()).hexdigest()[:12]
        _ext_key  = f"{mind_name}::{_sig_key}"
        _LOOP_COUNTERS[_ext_key] = _LOOP_COUNTERS.get(_ext_key, 0) + 1
        if _LOOP_COUNTERS[_ext_key] >= _EXTERNALIZE_THRESHOLD:
            _child_gen      = _fib_gen_of(mind_name) + 1
            _candidate_mind = _fib_spawn_name(mind_name, _child_gen, _sig_key)
            logger.info(
                "seed_mind_conversation: stable loop detected — %s (×%d) → spawn g%d: %s",
                _ext_key, _LOOP_COUNTERS[_ext_key], _child_gen, _candidate_mind,
            )
            await _bus_emit(YEventType.ENGINE_EXTERNALIZE, "y_engine", {
                **_engine_base_payload,
                "candidate_mind_name": _candidate_mind,
                "child_generation":    _child_gen,
                "signature":           _sig_key,
                "loop_count":          _LOOP_COUNTERS[_ext_key],
                "top3_entry_ids":      _top3_ids,
                "spiral":              _fib_spiral(_child_gen),
            })
            # Reset counter so it doesn't fire on every subsequent conversation
            _LOOP_COUNTERS[_ext_key] = 0
    else:
        # Loop did NOT stabilize — identity at pressure boundary (COLLAPSE risk)
        await _bus_emit(YEventType.ENGINE_COLLAPSE, "y_engine", _engine_base_payload)

    # Wire: stable resonance confirms these entries — bump version by 1.
    # Each confirmation is one act of "thinking in the same direction".
    # _crystallize reads version to upgrade claim_type: persistent thinking
    # → CONVICTION → ESTABLISHED_FACT → promoted_to_canon → belief_weight rises.
    # Only own entries are bumped (mind_name filter) — network entries are not
    # this mind's habit, they are borrowed signal.
    # NOTE: no commit here — we are inside a larger transaction managed by
    # the caller (add_founder_message). The UPDATE is part of that transaction.
    if stable and resonant:
        try:
            _resonant_ids = [r.entry_id for r in resonant]
            _id_phs = ", ".join(f":rid{i}" for i in range(len(_resonant_ids)))
            _rid_params = {f"rid{i}": str(v) for i, v in enumerate(_resonant_ids)}
            await db.execute(
                _text(f"""
                    UPDATE seed_mind_memory_entries
                    SET version = version + 1, updated_at = NOW()
                    WHERE id IN ({_id_phs})
                      AND mind_name = CAST(:mind_name AS TEXT)
                      AND is_current = true
                """),
                {**_rid_params, "mind_name": mind_name},
            )
        except Exception as _vexc:
            logger.debug("seed_mind_conversation: resonance version bump failed — %s", _vexc)

    # 5. Under pressure: no stability → self-expand before decoding (BRANCH)
    if not stable:
        await _self_expand(db, mind_name, resonant, founder_message)
        await _bus_emit(YEventType.ENGINE_BRANCH, "y_engine", {
            **_engine_base_payload,
            "synth_title": f"Reflection on: {resonant[0].title[:60]}" if resonant else "(empty)",
        })

    logger.debug(
        "seed_mind_conversation: own_entries=%d total=%d loop_depth=%d stable=%s — %s",
        len([e for e in all_entries if getattr(e, "mind_name", "") == mind_name]),
        len(all_entries), loop_depth, stable, mind_name,
    )

    # 6. State resonance + decode
    state_resonant = resonate_state(state_fp, all_entries, top_n=3)

    # Knowledge-gap detection: return an honest "I don't know yet" response
    # instead of assembling unrelated entries into a confusing answer.
    # Two independent triggers:
    #   A) Max resonance score is very low (< 0.15) — nothing matches well enough.
    #   B) The question's content tokens don't appear in ANY loaded entry — meaning
    #      the mind has never learned anything about this specific topic.
    #      Applies to ALL question types, not just factual starters.
    if intent == "questioning" and resonant:
        import re as _re_gap
        max_resonance = max(r.resonance for r in resonant)

        _gap = max_resonance < 0.15  # Case A: resonance too weak to trust

        # Case B: content tokens not found in any entry — topic is completely unknown
        if not _gap:
            _STOP = {
                "did", "was", "were", "we", "our", "us", "the", "a", "an",
                "is", "are", "it", "its", "that", "this", "what", "when",
                "which", "have", "has", "had", "been", "be", "do", "does",
                "you", "your", "i", "my", "me", "in", "on", "at", "for",
                "to", "of", "and", "or", "not", "no", "so", "if", "can",
                "will", "would", "could", "should", "also", "then", "too",
                "just", "now", "get", "make", "take", "give", "go", "way",
                "ready", "yet", "still", "any", "some", "all", "more", "its",
            }
            _q_content = {
                t for t in _re_gap.sub(r"[^\w]", " ", founder_message.lower()).split()
                if len(t) >= 4 and t not in _STOP
            }
            if _q_content:
                def _entry_text(e) -> str:
                    return f"{getattr(e, 'title', '')} {getattr(e, 'content', '')}".lower()
                # Count how many content tokens appear in entries
                _matched_tokens = {
                    tok for tok in _q_content
                    if any(tok in _entry_text(e) for e in all_entries)
                }
                # Gap if fewer than half the content tokens are known
                if len(_matched_tokens) < max(1, len(_q_content) // 2):
                    _gap = True

        if _gap and not _gap_already_answered:
            # Write the unknown question to the mind's subconscious so it can
            # reflect on it in the next oscillation pass — the mind holds it
            # as a QUESTION_TO_EXPLORE rather than returning a canned string.
            # Architecture rule: the mind speaks what it has, not what we wrote.
            try:
                await write_entry(
                    db,
                    mind_name=mind_name,
                    category=QUESTION_TO_EXPLORE,
                    title=f"gap: {founder_message[:80]}",
                    content=founder_message,
                    claim_type="OPEN_QUESTION",
                    tags="gap,subconscious_seed,pending",
                )
                logger.debug(
                    "seed_mind_conversation: gap seeded to subconscious — %s / %s",
                    mind_name, founder_message[:40],
                )
            except Exception as _ge:
                logger.debug("seed_mind_conversation: gap write failed — %s", _ge)
            # ENGINE_ATTACH: new motif (gap entry) attached to identity
            await _bus_emit(YEventType.ENGINE_ATTACH, "y_engine", {
                **_engine_base_payload,
                "title": f"gap: {founder_message[:80]}",
            })
            # Fall through — the mind speaks from what it currently holds.

    response = decode_pattern(mind_name, resonant, state_resonant, state_fp, intent, founder_message)

    # If decode returned nothing (no resonance at all), speak from mission/moral root
    # so the mind is never silent. Architecture rule: the mind speaks what it carries.
    if not response and all_entries:
        from app.core.pattern_encoder import _extract_mind_voice as _emv, ResonantEntry as _RE
        import re as _re
        _fallback_cats = ("MISSION_PURPOSE", "MORAL_ROOT", "WISDOM_EXTRACTED", "SELF_REFLECTION")
        _fb_raw = [e for e in all_entries if getattr(e, "category", "") in _fallback_cats]
        # Bias: MISSION_PURPOSE first so identity speaks before principles
        _fb_raw.sort(key=lambda e: 0 if getattr(e, "category", "") == "MISSION_PURPOSE" else 1)
        if _fb_raw:
            _fb_entries = [
                _RE(
                    entry_id=getattr(e, "id", ""),
                    mind_name=getattr(e, "mind_name", ""),
                    category=getattr(e, "category", ""),
                    title=getattr(e, "title", ""),
                    content=getattr(e, "content", ""),
                    claim_type=getattr(e, "claim_type", ""),
                    tags=getattr(e, "tags", ""),
                    resonance=0.0,
                )
                for e in _fb_raw[:5]
            ]
            _sents = _emv(_fb_entries, max_per_entry=1, total_max=2)
            # For greeting: skip negating "I am not..." statements
            if intent == "greeting":
                _sents = [s for s in _sents if not _re.match(r"^I am not\b", s, _re.IGNORECASE)]
            response = _sents[0] if _sents else ""
            if response:
                # Fell back to mission/moral root — wisdom returning to base identity
                await _bus_emit(YEventType.ENGINE_RETURN_TO_BASE, "y_engine", {
                    **_engine_base_payload,
                    "wisdom_title": response[:80],
                })

    return response, loop_depth


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class ConversationTurn:
    thread_id: str
    founder_message_id: str
    mind_message_id: str
    intent: str
    mind_response: str
    loop_depth: int = 1   # convergence iterations — the network's thinking depth


async def create_thread(
    db: AsyncSession,
    mind_name: str,
    user_id: str,
    title: str = "",
) -> SeedConversationThread:
    """Start a new conversation thread between a user and a named seed mind."""
    thread = SeedConversationThread(
        mind_name=mind_name,
        user_id=user_id,
        title=title or f"Thread with {mind_name}",
        intent="",
        thread_status=STATUS_OPEN,
    )
    db.add(thread)
    await db.commit()
    await db.refresh(thread)
    logger.info("seed_mind_conversation: thread created — %s / %s", mind_name, thread.id)
    return thread


async def add_founder_message(
    db: AsyncSession,
    thread_id: str,
    content: str,
) -> ConversationTurn:
    """Record a founder message, generate a mind response from the convergence loop."""
    # Load thread
    result = await db.execute(
        select(SeedConversationThread).where(SeedConversationThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()
    if thread is None:
        raise ValueError(f"Thread not found: {thread_id!r}")
    if thread.thread_status in (STATUS_ARCHIVED,):
        raise ValueError(f"Thread {thread_id!r} is archived and cannot accept new messages.")

    intent = classify_intent(content)

    # Load conversation history BEFORE flushing the new message — gives the
    # response engine full context of what was said so far in this thread.
    _history_result = await db.execute(
        select(SeedConversationMessage)
        .where(SeedConversationMessage.thread_id == thread_id)
        .order_by(SeedConversationMessage.created_at.asc())
    )
    _thread_history = list(_history_result.scalars().all())

    # Emit: message received by the pipeline
    try:
        await _bus_emit(
            YEventType.PATTERN_RECEIVED,
            source_service=thread.mind_name,
            payload={"intent": intent, "mind": thread.mind_name, "thread_id": thread_id},
        )
    except Exception:
        pass

    # Write founder message
    founder_msg = SeedConversationMessage(
        thread_id=thread_id,
        role=ROLE_FOUNDER,
        content=content,
        intent_type=intent,
    )
    db.add(founder_msg)
    await db.flush()

    # Compose mind response — pass history so the engine can avoid repeat questions
    # and write gap answers to memory.
    mind_response_text, _loop_depth = await _compose_mind_response(
        db, thread.mind_name, content, intent, history=_thread_history
    )

    # Moral gate — PUBLIC_CONTENT check before returning any response
    try:
        gate = await _moral_check(
            mind_response_text, ActionRisk.PUBLIC_CONTENT,
            source_service=thread.mind_name,
            mind_name=thread.mind_name,
        )
        if gate.verdict == GateVerdict.BLOCK:
            mind_response_text = "I'm not able to provide that response."
            logger.warning(
                "seed_mind_conversation: moral gate BLOCKED response for %s",
                thread.mind_name,
            )
            try:
                await _bus_emit(
                    YEventType.ENGINE_QUARANTINE,
                    source_service=thread.mind_name,
                    payload={"verdict": "BLOCK", "mind": thread.mind_name, "thread_id": thread_id},
                )
                await _bus_emit(
                    YEventType.MORAL_RISK_DETECTED,
                    source_service=thread.mind_name,
                    payload={"verdict": "BLOCK", "mind": thread.mind_name, "thread_id": thread_id},
                )
            except Exception:
                pass
        elif gate.verdict == GateVerdict.WARN:
            logger.info(
                "seed_mind_conversation: moral gate WARN for %s (score=%.2f)",
                thread.mind_name, gate.moral_score,
            )
    except Exception as gate_exc:
        logger.warning("seed_mind_conversation: moral gate error — %s", gate_exc)

    # Write mind response message
    mind_msg = SeedConversationMessage(
        thread_id=thread_id,
        role=ROLE_MIND,
        content=mind_response_text,
        intent_type=intent,
    )
    db.add(mind_msg)

    # Update thread
    thread.message_count += 2
    thread.updated_at = datetime.now(timezone.utc)
    if not thread.intent:
        thread.intent = intent
    if thread.title == f"Thread with {thread.mind_name}" and len(content) > 0:
        thread.title = content[:60].strip()
    db.add(thread)
    await db.commit()
    await db.refresh(founder_msg)
    await db.refresh(mind_msg)

    logger.info(
        "seed_mind_conversation: turn added — thread %s, intent %s, loop_depth=%d",
        thread_id, intent, _loop_depth,
    )

    # Meta-cognition: record this turn's performance so the mind can observe
    # its own thinking patterns and detect persistent knowledge edges.
    try:
        from app.core import meta_cognition as _mc
        _mc_fp = encode(content)
        _mc_domain = _mc_fp.dominant_domains[0] if _mc_fp.dominant_domains else "general"
        _mc_gap = "I don't have a specific memory" in mind_response_text
        _mc.record_turn(
            mind_name=thread.mind_name,
            domain=_mc_domain,
            loop_depth=_loop_depth,
            max_resonance=0.0,  # proxy — loop_depth is the primary signal
            gap_fired=_mc_gap,
        )
    except Exception:
        pass

    # Angel scaling — if the convergence loop ran more than once, fire one
    # OSCILLATION_REQUESTED event per additional depth level so angels pre-learn
    # before the next similar query.  This keeps min/max iteration time tight:
    # the angel work happens async, the response is already returned.
    if _loop_depth > 1:
        for _ in range(_loop_depth - 1):
            try:
                await _bus_emit(
                    YEventType.OSCILLATION_REQUESTED,
                    source_service=thread.mind_name,
                    payload={
                        "mind": thread.mind_name,
                        "reason": "loop_depth_scaling",
                        "depth": _loop_depth,
                    },
                )
            except Exception:
                pass

    return ConversationTurn(
        thread_id=thread_id,
        founder_message_id=founder_msg.id,
        mind_message_id=mind_msg.id,
        intent=intent,
        mind_response=mind_response_text,
        loop_depth=_loop_depth,
    )


async def get_threads(
    db: AsyncSession,
    mind_name: str,
    user_id: str = "",
    limit: int = 50,
) -> List[SeedConversationThread]:
    """Return conversation threads for a mind, optionally filtered by user."""
    stmt = select(SeedConversationThread).where(
        SeedConversationThread.mind_name == mind_name,
    )
    if user_id:
        stmt = stmt.where(SeedConversationThread.user_id == user_id)
    stmt = stmt.order_by(SeedConversationThread.updated_at.desc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_thread_messages(
    db: AsyncSession,
    thread_id: str,
) -> List[SeedConversationMessage]:
    """Return all messages in a thread, oldest first."""
    stmt = (
        select(SeedConversationMessage)
        .where(SeedConversationMessage.thread_id == thread_id)
        .order_by(SeedConversationMessage.created_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def escalate_to_archive(
    db: AsyncSession,
    thread_id: str,
    insight_summary: str,
) -> str:
    """Mark the thread ready_for_archive and write a summary to FounderArchiveMind memory."""
    from app.core.seed_mind_duplication import FOUNDER_ARCHIVE_MIND

    result = await db.execute(
        select(SeedConversationThread).where(SeedConversationThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()
    if thread is None:
        raise ValueError(f"Thread not found: {thread_id!r}")

    thread.thread_status = STATUS_READY_FOR_ARCHIVE
    thread.updated_at = datetime.now(timezone.utc)
    db.add(thread)

    entry = await write_entry(
        db,
        mind_name=FOUNDER_ARCHIVE_MIND,
        category=REFINED_FOUNDER_GUIDANCE,
        title=insight_summary[:80].strip(),
        content=insight_summary,
        claim_type="",
        tags=f"archived,thread:{thread_id},escalated",
        source_thread_id=thread_id,
    )
    await db.commit()

    logger.info(
        "seed_mind_conversation: thread %s escalated to archive, entry %s",
        thread_id, entry.id,
    )
    return entry.id
