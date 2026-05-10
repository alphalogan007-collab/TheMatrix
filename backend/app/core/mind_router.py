"""
mind_router.py — Central routing layer.

Architecture:
  Each mind is an index over its own knowledge domain.
  A question is encoded into a concept fingerprint.
  The router finds the mind whose purpose fingerprint overlaps most
  with that question — then routes the question to THAT mind only.

  This is the service registry for the distributed architecture:

    ┌──────────────────────────────────────────────────────┐
    │  Central Router  (this file)                         │
    │  - holds one lightweight MindFingerprint per mind    │
    │  - routing = pure in-memory dot-product computation  │
    │  - no knowledge of individual entries                │
    └──────────────────────────────────────────────────────┘
              ↓ route(question_fp) → best mind name(s)
    ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
    │  energy_mind │   │  quantum_mind│   │  legal_mind  │  ...
    │  own entries │   │  own entries │   │  own entries │
    │  own loop    │   │  own loop    │   │  own loop    │
    └──────────────┘   └──────────────┘   └──────────────┘

  Within the current monolith: minds share one DB but routing still
  works identically — the router knows each mind's domain vector and
  routes before touching any knowledge entries.

  In future distributed form: each mind is a separate service.
  On startup, the mind service POSTs its purpose text + entry_count
  to the central router via register_service(). The router stores only
  the fingerprint — not the knowledge. This is all it needs to route.

  The knowledge never leaves the mind service. The central layer is
  stateless with respect to knowledge. Only the fingerprint registry
  lives centrally. This is what keeps performance constant regardless
  of how many minds exist or where they run.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pattern_encoder import CONCEPT_DOMAINS, ConceptFingerprint, encode

logger = logging.getLogger(__name__)

_REFRESH_SECONDS: int = 300   # refresh fingerprints every 5 minutes
_MIN_SCORE: float = 0.01      # minimum routing score to be considered


# ---------------------------------------------------------------------------
# MindFingerprint — lightweight routing descriptor for one mind
# ---------------------------------------------------------------------------

@dataclass
class MindFingerprint:
    """The only thing the router knows about a mind.

    Built from the mind's MISSION_PURPOSE + REALITY_FRAMEWORK entries.
    This is a vector in CONCEPT_DOMAINS space that says:
    "this is the domain this mind operates in."

    Also stores raw_tokens from the purpose text so the router can do
    fine-grained keyword matching beyond the 21-domain abstraction layer.
    "fusion", "quantum", "semiconductor" etc. are not CONCEPT_DOMAIN keywords,
    but they DO appear in energy_mind's purpose text — so keyword matching
    routes them correctly even when domain scores are equal.

    In the distributed architecture this is what a remote mind service
    sends to the central router on startup — nothing else. The router
    never needs to see the mind's actual knowledge entries.
    """
    mind_name: str
    fp: ConceptFingerprint
    dominant_domains: List[str]         # top 3 concept domains for this mind
    entry_count: int                    # how many knowledge entries (confidence signal)
    purpose_tokens: Dict[str, float] = field(default_factory=dict)  # {token: idf_weight}
    purpose_summary: str = ""           # one-line purpose (for routing explain)
    service_url: Optional[str] = None   # None = local monolith, str = remote service URL
    reflected_count: int = 1            # SELF_REFLECTION count; 0 = still integrating (meditation damper)


# ---------------------------------------------------------------------------
# MindRouter — the central routing table
# ---------------------------------------------------------------------------

class MindRouter:
    """Routes questions to the best-fit mind by concept domain overlap.

    The routing computation is purely in-memory:
      encode(question) → ConceptFingerprint
      for each mind: dot(question_fp.domains, mind_fp.domains) → score
      return top-k minds sorted by score

    This makes routing O(n_minds × n_domains) = effectively instant
    regardless of how many entries each mind holds or where minds run.
    The fingerprints fit in a few KB of RAM for hundreds of minds.
    """

    def __init__(self) -> None:
        self._fingerprints: Dict[str, MindFingerprint] = {}
        self._lock: asyncio.Lock = asyncio.Lock()
        self._last_built: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Build / refresh
    # ------------------------------------------------------------------

    async def build(self, db: AsyncSession) -> None:
        """Build fingerprints for all registered minds from their purpose entries.

        Reads MISSION_PURPOSE + REALITY_FRAMEWORK entries from DB.
        Only own entries are used (not inherited seed_mind base) so the
        fingerprint reflects this mind's specific domain, not the collective.

        IDF weighting: tokens that appear in many minds' purpose texts get low
        weight (they don't differentiate minds — e.g. "system", "build").
        Specialist tokens unique to one mind get high weight (e.g. "fusion",
        "semiconductor", "quantum") so routing is precise.
        """
        import math
        import re as _re
        from app.core.seed_mind_store import MIND_BASE_REGISTRY, SEED_MIND, get_own_entries
        from app.core.seed_mind_memory import MISSION_PURPOSE, REALITY_FRAMEWORK

        _STOPWORDS = frozenset({
            "i", "a", "an", "the", "is", "it", "to", "in", "of", "and", "or",
            "that", "this", "my", "me", "we", "you", "be", "for", "on", "with",
            "at", "by", "from", "as", "but", "not", "are", "was", "were", "has",
            "have", "had", "do", "did", "will", "would", "could", "should", "can",
            "so", "if", "then", "also", "just", "get", "got", "its", "about",
            "up", "out", "no", "they", "their", "them", "your", "his", "her",
            "he", "she", "s", "am", "all", "hold", "holds", "which", "our",
            "across", "through", "into", "over", "under", "each", "mind",
        })

        all_minds = list(MIND_BASE_REGISTRY.keys()) + [SEED_MIND]
        raw: Dict[str, dict] = {}  # mind_name -> {fp, tokens, entry_count, purpose_summary}

        # Pre-load SELF_REFLECTION counts for all minds in one query
        # Used by the meditation damper: minds with 0 reflections get 0.3× routing weight
        from sqlalchemy import text as _rt
        _sr_rows = await db.execute(
            _rt("""
                SELECT mind_name, COUNT(*) FROM seed_mind_memory_entries
                WHERE category = 'SELF_REFLECTION' AND is_current = true
                GROUP BY mind_name
            """)
        )
        _reflected_counts: Dict[str, int] = {r[0]: r[1] for r in _sr_rows.fetchall()}

        # Pass 1: load all minds, collect raw tokens
        for mind_name in all_minds:
            try:
                purpose_entries = await get_own_entries(
                    db, mind_name=mind_name, category=MISSION_PURPOSE, limit=10,
                )
                framework_entries = await get_own_entries(
                    db, mind_name=mind_name, category=REALITY_FRAMEWORK, limit=10,
                )
                own_entries = purpose_entries + framework_entries
                if not own_entries:
                    continue

                combined_text = " ".join(
                    f"{e.title} {e.content}" for e in own_entries[:8]
                )
                fp = encode(combined_text)

                tokens = {
                    t.lower() for t in _re.split(r'\W+', combined_text)
                    if len(t) > 2 and t.lower() not in _STOPWORDS
                }

                purpose_summary = ""
                if purpose_entries:
                    first = purpose_entries[0].content
                    m = _re.search(r'[^.!?]+[.!?]', first)
                    purpose_summary = (m.group(0) if m else first[:120]).strip()

                raw[mind_name] = {
                    "fp": fp, "tokens": tokens,
                    "entry_count": len(own_entries),
                    "purpose_summary": purpose_summary,
                    "reflected_count": _reflected_counts.get(mind_name, 0),
                }
            except Exception as exc:
                logger.debug("mind_router: fingerprint build failed for %s: %s", mind_name, exc)

        if not raw:
            logger.warning("mind_router: no minds loaded — DB may be empty")
            self._last_built = datetime.now(timezone.utc)
            return

        # Pass 2: compute IDF — 1 / log(1 + df) where df = how many minds contain the token
        # Tokens in only ONE mind: idf ≈ 1.44 (high specificity)
        # Tokens in ALL minds: idf ≈ 0.15 (low specificity — generic terms)
        token_df: Dict[str, int] = {}  # token -> document frequency (# minds)
        for data in raw.values():
            for t in data["tokens"]:
                token_df[t] = token_df.get(t, 0) + 1
        idf: Dict[str, float] = {
            t: 1.0 / math.log(1.0 + df) for t, df in token_df.items()
        }

        # Pass 3: build final fingerprints with IDF-weighted token dicts
        built = 0
        for mind_name, data in raw.items():
            weighted_tokens: Dict[str, float] = {
                t: idf.get(t, 0.0) for t in data["tokens"]
            }
            self._fingerprints[mind_name] = MindFingerprint(
                mind_name=mind_name,
                fp=data["fp"],
                dominant_domains=data["fp"].dominant_domains[:3],
                entry_count=data["entry_count"],
                purpose_tokens=weighted_tokens,
                purpose_summary=data["purpose_summary"],
                reflected_count=data.get("reflected_count", 0),
            )
            built += 1

        self._last_built = datetime.now(timezone.utc)
        logger.info("mind_router: built %d mind fingerprints (IDF over %d tokens)", built, len(idf))

        # Emit graph snapshot so any SSE listener can update the visual graph
        try:
            from app.core.y_event_bus import YEventType, emit
            await emit(
                YEventType.MIND_GRAPH_UPDATED,
                source_service="mind_router",
                payload={
                    "nodes": self.graph_nodes(),
                    "edges": self.graph_edges(),
                },
            )
        except Exception:
            pass  # graph event is informational — never block routing

    async def refresh_if_stale(self, db: AsyncSession) -> None:
        """Refresh if fingerprints have never been built or are older than _REFRESH_SECONDS."""
        if self._last_built is None:
            async with self._lock:
                if self._last_built is None:  # double-checked locking
                    await self.build(db)
            return

        age = (datetime.now(timezone.utc) - self._last_built).total_seconds()
        if age > _REFRESH_SECONDS:
            async with self._lock:
                # Re-check after acquiring lock (another coroutine may have refreshed)
                age = (datetime.now(timezone.utc) - self._last_built).total_seconds()
                if age > _REFRESH_SECONDS:
                    await self.build(db)

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def route(
        self,
        question_fp: ConceptFingerprint,
        top_k: int = 3,
        exclude: Optional[List[str]] = None,
        require_min_entries: int = 1,
    ) -> List[Tuple[str, float]]:
        """Find the best-fit minds for this question fingerprint.

        Returns [(mind_name, score)] sorted by score descending.
        Score = domain overlap between question and mind's purpose fingerprint,
        plus a small confidence boost for minds with more knowledge entries.

        Args:
            question_fp:        encoded question
            top_k:              how many minds to return
            exclude:            mind names to skip (e.g. already answered)
            require_min_entries: skip minds with fewer than this many entries
        """
        exclude_set = set(exclude or [])
        scored: List[Tuple[float, str]] = []

        # Passive / observer minds that should NEVER be routing targets.
        # Soulmate minds are mirrors — they observe a user, they do not answer questions.
        # User minds are personal journals — substantive questions should not route to them.
        # These are excluded by suffix so any dynamically created soulmate is also excluded.
        _PASSIVE_SUFFIXES = ("_soulmate",)
        _PASSIVE_PREFIXES = ()  # extend later if needed

        # Question's raw content tokens for IDF-weighted keyword matching
        q_tokens = set(question_fp.raw_tokens)

        for mind_name, mfp in self._fingerprints.items():
            if mind_name in exclude_set:
                continue
            if mfp.entry_count < require_min_entries:
                continue
            # Always skip passive observer minds — they are not question answerers
            if any(mind_name.endswith(sfx) for sfx in _PASSIVE_SUFFIXES):
                continue

            # --- Signal 1: Domain overlap (21-dim abstract concept space) ---
            # Good for broad categories: technology, morality, mission, etc.
            domain_score = sum(
                question_fp.domains.get(d, 0.0) * mfp.fp.domains.get(d, 0.0)
                for d in CONCEPT_DOMAINS
            )

            # --- Signal 2: IDF-weighted keyword overlap ---
            # Each matched token contributes its IDF weight (how specific it is).
            # "fusion" appears in only energy_mind's tokens → high IDF → strong match.
            # "system" appears in every mind's tokens → low IDF → weak signal.
            # This is what makes specialist routing accurate.
            if q_tokens and mfp.purpose_tokens:
                # purpose_tokens is now {token: idf_weight}
                keyword_score = sum(
                    mfp.purpose_tokens.get(t, 0.0) for t in q_tokens
                ) / max(len(q_tokens), 1)
            else:
                keyword_score = 0.0

            # Hybrid: IDF keyword match dominates (0.65), domain provides structure (0.35)
            score = domain_score * 0.35 + keyword_score * 0.65

            # Meditation damper: a mind that has never reflected is still integrating.
            # Reduce its routing weight so traffic naturally flows to minds that have
            # synthesised their knowledge into SELF_REFLECTION. The damper lifts as
            # soon as the mind completes its first reflection (reflected_count refreshed
            # on next router build cycle).
            if mfp.reflected_count == 0:
                score *= 0.3  # damper — prefer integrated minds

            if score >= _MIN_SCORE:
                scored.append((score, mind_name))

        scored.sort(reverse=True)
        return [(name, score) for score, name in scored[:top_k]]

    def explain_route(
        self,
        question_fp: ConceptFingerprint,
        mind_name: str,
    ) -> dict:
        """Return a human-readable explanation of why this mind was chosen.

        Useful for debugging and for surfacing routing reasoning to the founder.
        """
        mfp = self._fingerprints.get(mind_name)
        if not mfp:
            return {"mind_name": mind_name, "reason": "not in registry"}

        matched_domains = [
            d for d in mfp.dominant_domains
            if question_fp.domains.get(d, 0.0) > 0.1
        ]
        return {
            "mind_name": mind_name,
            "dominant_domains": mfp.dominant_domains,
            "matched_domains": matched_domains,
            "purpose_summary": mfp.purpose_summary,
            "entry_count": mfp.entry_count,
        }

    # ------------------------------------------------------------------
    # Remote service registration (future distributed architecture)
    # ------------------------------------------------------------------

    def register_service(
        self,
        mind_name: str,
        purpose_text: str,
        entry_count: int,
        service_url: str,
    ) -> None:
        """Register a remote mind service.

        Called by mind services on their own startup in the distributed
        architecture. The service sends only its purpose description and
        entry count — the central router needs nothing else to route.

        The central app stores only the fingerprint, not the knowledge.
        Knowledge stays in the service that owns it.
        """
        fp = encode(purpose_text)
        import re as _re
        _SW = frozenset({"i","a","an","the","is","it","to","in","of","and","or","be","for","on","with","by","as","are","was","has","have","do","so","if","no","not","my","me","we","you","they","our","all","get","got","can","will","do","did","mind"})
        # For remote registration, no IDF context available — use uniform weights
        tokens_raw = {t.lower() for t in _re.split(r'\W+', purpose_text) if len(t) > 2 and t.lower() not in _SW}
        weighted_tokens = {t: 1.0 for t in tokens_raw}  # uniform weight for remote services
        m = _re.search(r'[^.!?]+[.!?]', purpose_text)
        summary = (m.group(0) if m else purpose_text[:120]).strip()

        self._fingerprints[mind_name] = MindFingerprint(
            mind_name=mind_name,
            fp=fp,
            dominant_domains=fp.dominant_domains[:3],
            entry_count=entry_count,
            purpose_tokens=weighted_tokens,
            purpose_summary=summary,
            service_url=service_url,
        )
        logger.info(
            "mind_router: registered remote service '%s' at %s (domains: %s)",
            mind_name, service_url, fp.dominant_domains[:3],
        )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def all_minds(self) -> List[str]:
        """Return all registered mind names."""
        return list(self._fingerprints.keys())

    def get_fingerprint(self, mind_name: str) -> Optional[MindFingerprint]:
        return self._fingerprints.get(mind_name)

    def registry_summary(self) -> List[dict]:
        """Return a summary of all registered minds (for /mind-router/registry endpoint)."""
        return [
            {
                "mind_name": mfp.mind_name,
                "dominant_domains": mfp.dominant_domains,
                "entry_count": mfp.entry_count,
                "purpose_summary": mfp.purpose_summary[:100],
                "is_remote": mfp.service_url is not None,
                "service_url": mfp.service_url,
            }
            for mfp in sorted(
                self._fingerprints.values(),
                key=lambda x: x.entry_count,
                reverse=True,
            )
        ]

    def graph_nodes(self) -> List[dict]:
        """Return all minds as graph nodes.

        Each node carries the metadata a graph renderer needs:
        id, entry_count, dominant_domains, purpose_summary, reflected_count.
        """
        return [
            {
                "id": mfp.mind_name,
                "label": mfp.mind_name.replace("_mind", "").replace("_", " "),
                "entry_count": mfp.entry_count,
                "dominant_domains": mfp.dominant_domains,
                "purpose_summary": mfp.purpose_summary[:100],
                "reflected": mfp.reflected_count > 0,
                "is_remote": mfp.service_url is not None,
            }
            for mfp in self._fingerprints.values()
        ]

    def graph_edges(self, min_weight: float = 0.05) -> List[dict]:
        """Return domain-overlap edges between minds.

        An edge means two minds share conceptual territory — questions that
        reach one mind could plausibly route to the other.
        Only edges above min_weight are returned to keep the graph readable.
        """
        minds = list(self._fingerprints.values())
        edges: List[dict] = []
        for i, a in enumerate(minds):
            for b in minds[i + 1:]:
                weight = sum(
                    a.fp.domains.get(d, 0.0) * b.fp.domains.get(d, 0.0)
                    for d in CONCEPT_DOMAINS
                )
                if weight >= min_weight:
                    edges.append({
                        "source": a.mind_name,
                        "target": b.mind_name,
                        "weight": round(weight, 3),
                        "shared_domains": [
                            d for d in a.dominant_domains
                            if d in b.dominant_domains
                        ],
                    })
        return sorted(edges, key=lambda e: -e["weight"])

    @property
    def ready(self) -> bool:
        return bool(self._fingerprints)


# ---------------------------------------------------------------------------
# Module-level singleton — shared across all requests in this process
# ---------------------------------------------------------------------------

_router = MindRouter()


async def get_router(db: AsyncSession) -> MindRouter:
    """Return the shared router, refreshing fingerprints if stale.

    Usage in endpoint:
        router = await get_router(db)
        best = router.route(question_fp, top_k=1)
    """
    await _router.refresh_if_stale(db)
    return _router


async def route_question(
    db: AsyncSession,
    question: str,
    top_k: int = 3,
    exclude: Optional[List[str]] = None,
) -> List[Tuple[str, float]]:
    """Convenience function: encode question and route in one call.

    Returns [(mind_name, score)] sorted by score descending.
    """
    router = await get_router(db)
    question_fp = encode(question)
    return router.route(question_fp, top_k=top_k, exclude=exclude)
