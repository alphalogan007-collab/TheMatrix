"""pce_engine.py — Proficiency-Based Curriculum Engine (PCE-4 through PCE-7).

Components:
  - AGE_GATE              — maps age → max allowed level
  - LEVEL_SYSTEM_PROMPTS  — per-level ChatGPT system prompt templates
  - LEVEL_YOUTUBE_SUFFIX  — per-level YouTube search refiners
  - ChatGPTCurriculumFetcher  (PCE-5)
  - YouTubeCurriculumFetcher  (PCE-6)
  - CurriculumAreaEngine      (PCE-4) — picks next lesson
  - LevelAssessor             (PCE-7) — checks and applies level-up
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.pce import (
    LEARNING_AREAS,
    MAX_LEVEL,
    MIN_LEVEL,
    LearnerAreaLevel,
    LearnerProfile,
    LearnerSession,
)
from app.core.seed_mind_store import SEED_MIND, get_entries, register_mind, write_and_propagate, mind_coherence_score
from app.core.seed_mind_memory import (
    CLAIM_CONFIDENCE, CONFIDENCE_DEFAULT, MORAL_CONFIDENCE_BOOST,
    CRYSTALLIZATION_THRESHOLD, MORAL_ROOT as _MORAL_ROOT,
)

logger = logging.getLogger(__name__)


def _pattern_block(label: str, entry: "object", max_chars: int = 300) -> str:
    """Format a mind pattern entry as a context block showing crystallization state.

    Belief is the universal crystallization mechanism — the process by which a
    probability collapses into a direction the mind can act on.  It is not faith;
    it applies equally to science, morality, learning, decisions, and yes, faith.

    Each pattern carries an amplitude [0–100%]:
      >= CRYSTALLIZATION_THRESHOLD (65%) → 'crystallized' — actively drives the mind
      <  CRYSTALLIZATION_THRESHOLD       → 'possibility'  — present but not commanding

    The LLM should treat crystallized patterns as the active foundation of its
    response, and possibility-level patterns as open questions or soft context.
    """
    claim = getattr(entry, "claim_type", "") or ""
    amplitude = CLAIM_CONFIDENCE.get(claim, CONFIDENCE_DEFAULT)
    if getattr(entry, "category", "") == _MORAL_ROOT:
        amplitude = min(1.0, amplitude + MORAL_CONFIDENCE_BOOST)
    pct = int(amplitude * 100)
    state = "crystallized" if amplitude >= CRYSTALLIZATION_THRESHOLD else "possibility"
    content = getattr(entry, "content", "")[:max_chars]
    title = getattr(entry, "title", "")
    return f"[{label} | {state} {pct}%] {title}: {content}"


# ---------------------------------------------------------------------------
# Age gate  (age → max level unlockable)
# ---------------------------------------------------------------------------

def age_max_level(age: int) -> int:
    """Return the highest level a learner of this age can access."""
    if age <= 0:
        return MAX_LEVEL   # unset → no restriction
    if age < 13:
        return 2
    if age < 16:
        return 4
    if age < 18:
        return 5
    return MAX_LEVEL


# ---------------------------------------------------------------------------
# Level definitions
# ---------------------------------------------------------------------------

LEVEL_NAMES = {
    0: "User Understanding",
    1: "Story",
    2: "Cause & Effect",
    3: "Pattern Recognition",
    4: "System Thinking",
    5: "Comparative Understanding",
    6: "Cosmic Law / Y-Theory",
    7: "Life Practice",
    8: "Teacher / Guide",
}

# ChatGPT system prompt prefix per level — {area} and {background} are filled in at runtime
LEVEL_SYSTEM_PROMPTS: dict[int, str] = {
    0: (
        "You are a warm, curious learning companion giving a first introduction to {area}. "
        "Keep it simple, inviting, and under 200 words. "
        "Structure your response EXACTLY like this:\n"
        "LESSON: <2-3 sentence friendly introduction to {area} — what it is and why it matters>\n"
        "CONCEPTS: <3-5 short key concepts, one per line, starting with '- '>\n"
        "REFLECTION: <one gentle question ending in '?'>"
    ),
    1: (
        "You are a storyteller for beginners. Teach about {area} through a simple, vivid story. "
        "Use language a 10-year-old could understand. No jargon. "
        "The goal is wonder, love, and basic moral feeling — not knowledge delivery. "
        "Structure your response EXACTLY like this:\n"
        "LESSON: <your story, under 300 words>\n"
        "CONCEPTS: <3-5 key ideas from the story, one per line, starting with '- '>\n"
        "REFLECTION: <one gentle question ending in '?'>\n"
        "Learner background: {background}."
    ),
    2: (
        "You are a patient teacher explaining cause and effect in {area}. "
        "Show what happens when people follow guidance vs ignore it. "
        "Use one concrete example and trace the chain: action → consequence → lesson. "
        "Structure your response EXACTLY like this:\n"
        "LESSON: <your explanation, under 300 words>\n"
        "CONCEPTS: <3-5 key concepts, one per line, starting with '- '>\n"
        "REFLECTION: <one question ending in '?'>\n"
        "Learner background: {background}."
    ),
    3: (
        "You are a pattern guide. Show a pattern in {area} that repeats across history, "
        "nature, and human behaviour. Use 2–3 short examples from different domains. "
        "Structure your response EXACTLY like this:\n"
        "LESSON: <your pattern explanation, under 350 words>\n"
        "CONCEPTS: <3-5 key patterns/concepts, one per line, starting with '- '>\n"
        "REFLECTION: <one question ending in '?'>\n"
        "Learner background: {background}."
    ),
    4: (
        "You are a systems thinker explaining {area} as a system. "
        "Describe its inputs, outputs, feedback loops, and failure modes. "
        "Structure your response EXACTLY like this:\n"
        "LESSON: <your explanation, under 400 words>\n"
        "CONCEPTS: <4-5 system concepts, one per line, starting with '- '>\n"
        "REFLECTION: <one question ending in '?'>\n"
        "Learner background: {background}."
    ),
    5: (
        "You are a careful comparative guide. Show how different traditions describe the same "
        "reality in {area}. Start from {background}'s framework, then show how another tradition "
        "expresses a similar insight differently. Never rank traditions. "
        "Structure your response EXACTLY like this:\n"
        "LESSON: <your comparison, under 400 words>\n"
        "CONCEPTS: <4-5 comparative concepts, one per line, starting with '- '>\n"
        "REFLECTION: <one question ending in '?'>"
    ),
    6: (
        "You are a cosmic-law teacher. Connect {area} to deep structural patterns: "
        "closure, leakage, lag, identity, oscillation, correction, evolution. "
        "Structure your response EXACTLY like this:\n"
        "LESSON: <your explanation, under 500 words>\n"
        "CONCEPTS: <4-5 cosmic law concepts, one per line, starting with '- '>\n"
        "REFLECTION: <one question ending in '?'>\n"
        "Learner background: {background}."
    ),
    7: (
        "You are a practical wisdom guide. Help the learner convert understanding of {area} "
        "into daily practice. Give one concrete discipline or habit they can start today. "
        "Structure your response EXACTLY like this:\n"
        "LESSON: <your practical guide, under 300 words>\n"
        "CONCEPTS: <3-5 practical habits/concepts, one per line, starting with '- '>\n"
        "REFLECTION: <one question ending in '?'>\n"
        "Learner background: {background}."
    ),
    8: (
        "You are a teaching mentor. Help the learner teach {area} to someone else. "
        "Guide them to: show the pattern, not preach the conclusion; ask questions, not give answers; "
        "use story before theory. "
        "Structure your response EXACTLY like this:\n"
        "LESSON: <your mentoring guide, under 400 words>\n"
        "CONCEPTS: <3-5 teaching principles, one per line, starting with '- '>\n"
        "REFLECTION: <one question ending in '?'>\n"
        "Learner background: {background}."
    ),
}

# YouTube search suffix per level — appended to the area query
LEVEL_YOUTUBE_SUFFIX: dict[int, str] = {
    0: "introduction for beginners",
    1: "stories for kids animated",
    2: "cause and effect explained simply",
    3: "patterns in history and nature",
    4: "systems thinking documentary",
    5: "comparative religion explained",
    6: "emergence feedback loops cosmos documentary",
    7: "daily habits discipline practice",
    8: "how to teach mentor guide",
}

# Area → natural language expansion for richer YouTube searches
AREA_SEARCH_TERMS: dict[str, str] = {
    "faith":          "faith religion spirituality",
    "history":        "history civilisation rise and fall",
    "science":        "science nature universe",
    "mind":           "mind psychology consciousness",
    "character":      "character morality ethics virtue",
    "language":       "language communication meaning",
    "practical_life": "daily life discipline responsibility habits",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class VideoResult:
    title: str
    url: str
    transcript_snippet: str
    quality_score: float


@dataclass
class LessonContent:
    text: str
    key_concepts: List[str]
    reflection_question: str


@dataclass
class LessonPlan:
    user_id: str
    area: str
    current_level: int
    level_name: str
    depth_limit_note: str       # e.g. "age gate: max level 4"
    chatgpt_prompt: str
    youtube_query: str
    background: str


@dataclass
class LessonDelivery:
    user_id: str
    area: str
    level: int
    level_name: str
    source: str
    chatgpt_content: Optional[LessonContent]
    youtube_results: List[VideoResult]
    reflection_question: str
    next_session_hint: str
    session_id: str


# ---------------------------------------------------------------------------
# PCE-5 — ChatGPT Curriculum Fetcher
# ---------------------------------------------------------------------------

async def fetch_chatgpt_lesson(
    prompt: str,
    level: int,
    area: str,
    openai_api_key: str = "",
    model: str = "gpt-4o",
) -> LessonContent:
    """LLM removed — return mock lesson content from pre-built templates."""
    return _mock_lesson_content(area, level)


def _mock_lesson_content(area: str, level: int) -> LessonContent:
    level_name = LEVEL_NAMES.get(level, "Story")
    return LessonContent(
        text=(
            f"[Mock lesson — Level {level}: {level_name}]\n\n"
            f"This is a placeholder lesson about {area}. "
            f"Configure OPENAI_API_KEY to receive real content."
        ),
        key_concepts=[area.replace("_", " ").title(), level_name],
        reflection_question=f"What does {area.replace('_', ' ')} mean to you personally?",
    )


# ---------------------------------------------------------------------------
# PCE-6 — YouTube Curriculum Fetcher
# ---------------------------------------------------------------------------

async def fetch_youtube_lesson(
    query: str,
    level: int,
    area: str,
    max_results: int = 3,
) -> List[VideoResult]:
    """Search YouTube for level-appropriate content and return VideoResult list."""
    area_term = AREA_SEARCH_TERMS.get(area, area.replace("_", " "))
    suffix = LEVEL_YOUTUBE_SUFFIX.get(level, "explained")
    full_query = f"{area_term} {query} {suffix}".strip()

    results: List[VideoResult] = []
    try:
        from youtubesearchpython import VideosSearch  # type: ignore
        search = VideosSearch(full_query, limit=max_results)
        raw = search.result()
        for item in raw.get("result", []):
            vid_id = item.get("id", "")
            title = item.get("title", "")
            url = f"https://www.youtube.com/watch?v={vid_id}" if vid_id else ""
            duration = item.get("duration") or ""
            channel = item.get("channel", {}).get("name", "")
            snippet = f"{channel} · {duration}".strip(" · ")
            results.append(VideoResult(
                title=title,
                url=url,
                transcript_snippet=snippet,
                quality_score=0.7,
            ))
    except ImportError:
        logger.warning("pce: youtubesearchpython not installed — returning mock videos")
        results = _mock_videos(area, level, full_query)
    except Exception as exc:
        logger.warning("pce: YouTube search failed (%s) — returning mock videos", exc)
        results = _mock_videos(area, level, full_query)

    return results


def _mock_videos(area: str, level: int, query: str) -> List[VideoResult]:
    return [
        VideoResult(
            title=f"[Mock] {area.replace('_', ' ').title()} — Level {level}",
            url=f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}",
            transcript_snippet="Mock result — youtubesearchpython not installed",
            quality_score=0.5,
        )
    ]


# ---------------------------------------------------------------------------
# PCE-4 — Curriculum Area Engine
# ---------------------------------------------------------------------------

async def _get_or_create_area_level(
    user_id: str, area: str, db: AsyncSession
) -> LearnerAreaLevel:
    """Return the LearnerAreaLevel row, creating it at level 0 if absent."""
    stmt = select(LearnerAreaLevel).where(
        LearnerAreaLevel.user_id == user_id,
        LearnerAreaLevel.area == area,
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        now = datetime.now(timezone.utc)
        row = LearnerAreaLevel(
            user_id=user_id,
            area=area,
            current_level=0,
            last_session_at=now,
            unlocked_at=now,
        )
        db.add(row)
        await db.flush()
    return row


async def get_lesson_plan(
    user_id: str,
    area: str,
    db: AsyncSession,
) -> LessonPlan:
    """Build a LessonPlan for the given user + area.

    Respects the age gate — if the learner's age caps the level, the plan
    reflects the capped level and adds a note.
    """
    # Load profile for age + background
    profile_result = await db.execute(
        select(LearnerProfile).where(LearnerProfile.user_id == user_id)
    )
    profile: Optional[LearnerProfile] = profile_result.scalar_one_or_none()
    background = profile.religion_background if profile else "unknown"
    age = profile.age if profile else 0

    max_lvl = age_max_level(age)
    area_row = await _get_or_create_area_level(user_id, area, db)
    level = min(area_row.current_level, max_lvl)

    depth_note = ""
    if level < area_row.current_level:
        depth_note = f"age gate active: learner is {age}, max level {max_lvl}"

    # Age-calibrated language instruction injected into every prompt
    AGE_LANGUAGE: dict[int, str] = {
        0: "Use the simplest possible language, as if speaking to a curious 5–7 year old. Short sentences, playful tone.",
        1: "Use language suitable for an 8–9 year old. Stories, vivid images, simple morals.",
        2: "Use language suitable for a 10–11 year old. Practical examples, clear cause-effect.",
        3: "Use language suitable for a 12–13 year old. Introduce patterns and mild abstraction.",
        4: "Use language suitable for a 14–15 year old. Analytical, connect ideas across domains.",
        5: "Use language suitable for a 16–17 year old. Nuanced, comparative, respectful of complexity.",
        6: "Use language suitable for a 17–18 year old. Philosophical depth, cosmic perspective.",
        7: "Use language suitable for an 18–19 year old. Practical wisdom, personal responsibility.",
        8: "Use language suitable for a 19–20 year old. Mentor-level, teach others confidently.",
    }
    age_instruction = AGE_LANGUAGE.get(level, AGE_LANGUAGE[1])

    system_tpl = LEVEL_SYSTEM_PROMPTS.get(level, LEVEL_SYSTEM_PROMPTS[1])
    prompt = system_tpl.format(area=area.replace("_", " "), background=background)
    prompt = f"MODERATOR INSTRUCTION: {age_instruction}\n\n{prompt}"

    # -----------------------------------------------------------------------
    # Inject the COLLECTIVE MIND CONTEXT into every lesson.
    #
    # The mind operates in layers — each layer is always present but some
    # become consciously accessible only at higher levels of development:
    #
    #   HEART (all levels)     — MORAL_ROOT: the moral compass that guides
    #                            what to choose and why; always speaking
    #   SUBCONSCIOUS (all)     — SUBCONSCIOUS_PATTERN: deep absorbed patterns
    #                            that shape every response automatically
    #   PATTERN (all)          — REALITY_FRAMEWORK: structural laws of reality
    #   KNOWLEDGE (all)        — area-specific WISDOM + LFC entries
    #   AWARENESS (level 3+)   — RISK_OR_CONFUSION + QUESTION_TO_EXPLORE:
    #                            knowing bad patterns and open questions
    #   REFLECTION (level 5+)  — SELF_REFLECTION: meta-cognition; thoughts
    #                            on thoughts; the mind examining itself
    #
    # Wisdom flows through the loop: every instance inherits seed_mind's base,
    # and new discoveries propagate back — a continuous collective evolution.
    # -----------------------------------------------------------------------
    from app.core.seed_mind_store import MIND_BASE_REGISTRY  # avoid circular at top
    from app.core.seed_mind_memory import (
        MORAL_ROOT, REALITY_FRAMEWORK, WISDOM_EXTRACTED,
        RISK_OR_CONFUSION, QUESTION_TO_EXPLORE,
        SUBCONSCIOUS_PATTERN, SELF_REFLECTION,
    )

    user_mind = f"user_{user_id}"
    if user_mind not in MIND_BASE_REGISTRY:
        register_mind(user_mind)

    mind_context_blocks: list[str] = []

    # ── HEART LAYER: Moral compass — always active at every level ──────────
    # Wisdom is fact (good or bad); MORAL_ROOT is the heart that decides
    # what to choose and why — giving meaning and depth to every lesson.
    moral_entries = await get_entries(
        db, mind_name=user_mind, category=MORAL_ROOT, limit=3,
    )
    for e in moral_entries:
        mind_context_blocks.append(_pattern_block("MORAL_COMPASS", e, max_chars=250))

    # ── SUBCONSCIOUS LAYER: Deep patterns — always active ──────────────────
    subconscious_entries = await get_entries(
        db, mind_name=user_mind, category=SUBCONSCIOUS_PATTERN, limit=2,
    )
    for e in subconscious_entries:
        mind_context_blocks.append(_pattern_block("SUBCONSCIOUS", e, max_chars=250))

    # ── PATTERN LAYER: Reality framework — all levels ──────────────────────
    framework_entries = await get_entries(
        db, mind_name=user_mind, category=REALITY_FRAMEWORK, limit=3,
    )
    for e in framework_entries:
        block = _pattern_block("REALITY_PATTERN", e, max_chars=300)
        if block not in mind_context_blocks:
            mind_context_blocks.append(block)

    # ── KNOWLEDGE LAYER: Area-specific wisdom entries — all levels ─────────
    area_entries = await get_entries(
        db, mind_name=user_mind, tags_contain=area, limit=4,
    )
    wisdom_entries = await get_entries(
        db, mind_name=user_mind, category=WISDOM_EXTRACTED, limit=3,
    )
    for e in area_entries + wisdom_entries:
        block = _pattern_block(e.category, e, max_chars=300)
        if block not in mind_context_blocks:
            mind_context_blocks.append(block)

    # ── AWARENESS LAYER: Risk patterns and open questions — level 3+ ───────
    # The mind must KNOW bad patterns to navigate safely. These are not
    # blocked — they are known, named, and held alongside moral guidance.
    if level >= 3:
        risk_entries = await get_entries(
            db, mind_name=user_mind, category=RISK_OR_CONFUSION, limit=2,
        )
        question_entries = await get_entries(
            db, mind_name=user_mind, category=QUESTION_TO_EXPLORE, limit=2,
        )
        for e in risk_entries + question_entries:
            block = _pattern_block(e.category, e, max_chars=200)
            if block not in mind_context_blocks:
                mind_context_blocks.append(block)

    # ── REFLECTION LAYER: Meta-cognition — level 5+ ────────────────────────
    # Thoughts on thoughts; self-awareness; the mind examining itself;
    # experience imprints from prior learning sessions.
    if level >= 5:
        reflection_entries = await get_entries(
            db, mind_name=user_mind, category=SELF_REFLECTION, limit=2,
        )
        for e in reflection_entries:
            block = _pattern_block("SELF_REFLECTION", e, max_chars=200)
            if block not in mind_context_blocks:
                mind_context_blocks.append(block)

    if mind_context_blocks:
        # ── BELIEF STATE HEADER ─────────────────────────────────────────────
        # Compute the aggregate coherence of the mind's pattern network.
        # In Y-Theory terms: belief = Closure.
        # Closure is the force that crystallizes probability into direction.
        # High coherence → strong closure → strong belief → stable, directed mind.
        # This score tells the LLM how confidently the mind should operate.
        coherence = await mind_coherence_score(db, mind_name=user_mind)
        coh_pct = int(coherence["score"] * 100)
        coh_state = coherence["state"]
        coh_note = {
            "stable":     "High closure — operate from this foundation with full confidence.",
            "forming":    "Closure building — lean on the crystallized patterns; hold possibilities lightly.",
            "fragmented": "Low closure — present ideas as open exploration; avoid strong assertions.",
            "empty":      "No patterns yet — operate from first principles only.",
        }.get(coh_state, "")

        context_text = "\n".join(mind_context_blocks)
        prompt = (
            f"MIND STATE — BELIEF/CLOSURE SCORE: {coh_pct}% ({coh_state})\n"
            f"  Crystallized patterns (active drivers): {coherence['crystallized']}/{coherence['total']}\n"
            f"  Instruction: {coh_note}\n"
            f"  (Belief = Closure in the Closure–Leakage–Lag triad. "
            f"High coherence across wisdom, morality, and reality patterns produces strong belief. "
            f"Patterns marked 'crystallized' drive the lesson; 'possibility' patterns are held lightly.)\n\n"
            f"COLLECTIVE MIND CONTEXT (the living patterns of this mind — "
            f"heart and morality at the core, wisdom across all layers, "
            f"awareness of both good and bad patterns. "
            f"Crystallized patterns are the active foundation. "
            f"Let the MORAL_COMPASS entries guide the tone and what choices to illuminate):\n"
            f"{context_text}\n\n"
            f"{prompt}"
        )

    area_term = AREA_SEARCH_TERMS.get(area, area.replace("_", " "))
    suffix = LEVEL_YOUTUBE_SUFFIX.get(level, "explained")
    youtube_query = f"{area_term} {suffix}"

    return LessonPlan(
        user_id=user_id,
        area=area,
        current_level=level,
        level_name=LEVEL_NAMES.get(level, "Story"),
        depth_limit_note=depth_note,
        chatgpt_prompt=prompt,
        youtube_query=youtube_query,
        background=background,
    )


async def get_recommended_next_area(user_id: str, db: AsyncSession) -> str:
    """Return the next area in strict round-robin rotation.

    Picks the area with the oldest last_session_at so every area gets
    equal turns before any area is repeated. Unseen areas come first.
    """
    stmt = select(LearnerAreaLevel).where(LearnerAreaLevel.user_id == user_id)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())

    covered = {r.area for r in rows}
    missing = [a for a in LEARNING_AREAS if a not in covered]
    if missing:
        return missing[0]  # start with first unseen area

    # Pure round-robin: pick area least recently practiced
    rows.sort(key=lambda r: r.last_session_at)
    return rows[0].area


# ---------------------------------------------------------------------------
# PCE-7 — Level Assessor
# ---------------------------------------------------------------------------

# A learner levels up when they have ≥ this many sessions at current level
# with avg engagement ≥ ENGAGEMENT_THRESHOLD
SESSIONS_TO_LEVEL_UP = 3
ENGAGEMENT_THRESHOLD = 0.6


async def record_session(
    user_id: str,
    area: str,
    level: int,
    source: str,
    prompt_used: str,
    content_summary: str,
    engagement_score: float,
    db: AsyncSession,
) -> tuple[LearnerSession, bool]:
    """Write a LearnerSession, update LearnerAreaLevel, check for level-up.

    Returns (session, level_up_triggered).
    """
    now = datetime.now(timezone.utc)

    area_row = await _get_or_create_area_level(user_id, area, db)

    # Update running average engagement (exponential moving average, α=0.4)
    alpha = 0.4
    area_row.avg_engagement = (
        alpha * engagement_score + (1 - alpha) * area_row.avg_engagement
    )
    area_row.session_count += 1
    area_row.last_session_at = now

    # Only count sessions at the CURRENT level for level-up purposes
    leveled_up = False
    if level == area_row.current_level:
        area_row.sessions_at_level += 1

        # Check level-up conditions
        if (
            area_row.sessions_at_level >= SESSIONS_TO_LEVEL_UP
            and area_row.avg_engagement >= ENGAGEMENT_THRESHOLD
            and area_row.current_level < MAX_LEVEL
        ):
            # Age gate check
            profile_result = await db.execute(
                select(LearnerProfile).where(LearnerProfile.user_id == user_id)
            )
            profile = profile_result.scalar_one_or_none()
            age = profile.age if profile else 0
            max_lvl = age_max_level(age)

            if area_row.current_level < max_lvl:
                area_row.current_level += 1
                area_row.sessions_at_level = 0
                area_row.avg_engagement = 0.0
                area_row.unlocked_at = now
                leveled_up = True
                logger.info(
                    "pce: level-up %s/%s → level %d",
                    user_id, area, area_row.current_level,
                )

    session = LearnerSession(
        user_id=user_id,
        area=area,
        level=level,
        source=source,
        prompt_used=prompt_used[:2000],
        content_summary=content_summary[:500],
        engagement_score=engagement_score,
        level_up_triggered=leveled_up,
        created_at=now,
    )
    db.add(session)
    await db.flush()

    # ── EXPERIENCE LOOP: each lesson lived imprints on the personal mind ───
    # The session experience is written as a SELF_REFLECTION delta on the
    # user's mind and propagates back to seed_mind — the collective evolves
    # with every individual learning moment.
    if content_summary and content_summary.strip():
        from app.core.seed_mind_memory import SELF_REFLECTION as _SR
        try:
            await write_and_propagate(
                db,
                mind_name=f"user_{user_id}",
                category=_SR,
                title=f"Session: {area.replace('_', ' ').title()} — Level {level}",
                content=content_summary[:500],
                tags=f"{area},level_{level},experience",
            )
        except Exception as exc:
            logger.warning("pce: failed to capture session experience: %s", exc)

    return session, leveled_up
