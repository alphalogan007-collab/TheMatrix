"""routes_seed_mind_conversation.py — Founder ↔ seed-mind conversation endpoints.

Architecture: stateless. History lives on the client.
The mind writes only to its own memory (learning), never to conversation tables.

Endpoints:
  POST /seed-mind/conversation/message              — send + get mind response (stateless)
  POST /seed-mind/conversation/stream-message       — SSE stream (stateless)
  GET  /seed-mind/conversation/intents              — list intent types

Legacy thread endpoints kept for the /mind browser UI only (to be removed):
  POST /seed-mind/conversation/threads              — create a thread
  POST /seed-mind/conversation/threads/{id}/message — send a founder message
  GET  /seed-mind/conversation/threads
  GET  /seed-mind/conversation/threads/{id}/messages
  POST /seed-mind/conversation/threads/{id}/escalate
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.seed_mind_conversation import (
    ALL_INTENTS,
    ConversationTurn,
    INTENT_INSTRUCTION,
    ROLE_FOUNDER,
    ROLE_MIND,
    STATUS_ARCHIVED,
    STATUS_OPEN,
    add_founder_message,
    classify_intent,
    create_thread,
    escalate_to_archive,
    get_thread_messages,
    get_threads,
)
from app.db.session import AsyncSessionDep
from app.models.seed_conversation import SeedConversationMessage, SeedConversationThread

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class CreateThreadIn(BaseModel):
    mind_name: str
    user_id: str = ""
    title: str = ""


class ThreadOut(BaseModel):
    id: str
    mind_name: str
    user_id: str
    title: str
    intent: str
    thread_status: str
    message_count: int


class SendMessageIn(BaseModel):
    content: str


class ConversationTurnOut(BaseModel):
    thread_id: str
    founder_message_id: str
    mind_message_id: str
    intent: str
    mind_response: str
    loop_depth: int = 1   # convergence iterations — the network's thinking depth


class MessageOut(BaseModel):
    id: str
    thread_id: str
    role: str
    content: str
    intent_type: str
    memory_entry_id: str


class EscalateIn(BaseModel):
    insight_summary: str


class EscalateOut(BaseModel):
    archive_entry_id: str


# Stateless endpoint schemas — no thread IDs, history comes from client
class HistoryMessage(BaseModel):
    role: str     # "founder" or "mind"
    content: str


class StatelessMessageIn(BaseModel):
    mind_name: str
    content: str
    history: List[HistoryMessage] = []
    loop_size: int = 1


# ---------------------------------------------------------------------------
# Stateless endpoints (new architecture — no conversation DB)
# ---------------------------------------------------------------------------

@router.post(
    "/stream-message",
    summary="Stream a message to a mind — stateless, history from client",
    response_class=StreamingResponse,
)
async def stream_message_stateless(
    body: StatelessMessageIn,
) -> StreamingResponse:
    """Send a message to a mind and receive SSE response stream.

    No thread, no DB conversation storage. History is passed in the request.
    The mind learns through resonance (memory entries) — not through stored conversations.

    SSE format:
      data: {"step":1,"total":1,"mind_name":"...","response":"...","loop_depth":3,"is_final":true}
    """
    from app.core.mind_loop import stream_fractal_loop, LOOP_SIZE_MAX
    from app.db.session import AsyncSessionLocal

    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Content must not be empty")

    mind_name = body.mind_name.strip()
    if not mind_name:
        raise HTTPException(status_code=422, detail="mind_name must not be empty")

    loop_size = max(1, min(body.loop_size, LOOP_SIZE_MAX))
    intent = classify_intent(content)

    # Convert client history to the simple objects _compose_mind_response expects
    class _HMsg:
        def __init__(self, role: str, content: str):
            self.role = role
            self.content = content
    history = [_HMsg(h.role, h.content) for h in body.history]

    # If instruction intent — propagate directive in background
    try:
        from app.core.founder_directive import is_founder_message, propagate_directive
        if is_founder_message(mind_name) and intent == INTENT_INSTRUCTION:
            _captured_content = content
            _captured_mind = mind_name

            async def _bg_propagate() -> None:
                try:
                    from app.db.session import AsyncSessionLocal as _ASL2
                    async with _ASL2() as dir_db:
                        await propagate_directive(dir_db, _captured_content, _captured_mind)
                except Exception as _bg_exc:
                    logger.warning("stream_message_stateless: directive propagation failed -- %s", _bg_exc)

            import asyncio as _asyncio_bg
            _asyncio_bg.create_task(_bg_propagate())
    except Exception as _dir_exc:
        logger.warning("stream_message_stateless: directive setup failed -- %s", _dir_exc)

    async def _generate() -> AsyncGenerator[bytes, None]:
        import asyncio as _aio
        _q: _aio.Queue = _aio.Queue()
        _DONE = object()

        async def _pump() -> None:
            try:
                async with AsyncSessionLocal() as loop_db:
                    async for step in stream_fractal_loop(
                        db=loop_db,
                        coordinator_mind=mind_name,
                        content=content,
                        intent=intent,
                        history=history,
                        loop_size=loop_size,
                    ):
                        await _q.put(step)
            finally:
                await _q.put(_DONE)

        async def _keepalive() -> None:
            while True:
                await _aio.sleep(5)
                await _q.put(b": ping\n\n")

        _pump_task = _aio.create_task(_pump())
        _ping_task = _aio.create_task(_keepalive())

        try:
            while True:
                item = await _q.get()
                if item is _DONE:
                    break
                if isinstance(item, bytes):
                    yield item
                    continue
                yield f"data: {json.dumps(item.to_dict())}\n\n".encode()
        except Exception as exc:
            logger.warning("stream_message_stateless: loop error — %s", exc)
            yield f"data: {json.dumps({'error': str(exc), 'is_final': True})}\n\n".encode()
        finally:
            _ping_task.cancel()
            _pump_task.cancel()

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/intents", response_model=List[str])
async def list_intents() -> List[str]:
    """Return all supported intent type constants."""
    return ALL_INTENTS


@router.post("/threads", response_model=ThreadOut, status_code=status.HTTP_201_CREATED)
async def start_thread(body: CreateThreadIn, db: AsyncSessionDep) -> ThreadOut:
    """Start a new conversation thread between a user and a named seed mind."""
    thread = await create_thread(db, mind_name=body.mind_name, user_id=body.user_id, title=body.title)
    return ThreadOut(
        id=thread.id,
        mind_name=thread.mind_name,
        user_id=thread.user_id,
        title=thread.title,
        intent=thread.intent,
        thread_status=thread.thread_status,
        message_count=thread.message_count,
    )


@router.post(
    "/threads/{thread_id}/message",
    response_model=ConversationTurnOut,
    status_code=status.HTTP_200_OK,
)
async def send_message(
    thread_id: str,
    body: SendMessageIn,
    db: AsyncSessionDep,
) -> ConversationTurnOut:
    """Send a founder message, receive a mind response."""
    try:
        turn: ConversationTurn = await add_founder_message(
            db,
            thread_id=thread_id,
            content=body.content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return ConversationTurnOut(
        thread_id=turn.thread_id,
        founder_message_id=turn.founder_message_id,
        mind_message_id=turn.mind_message_id,
        intent=turn.intent,
        mind_response=turn.mind_response,
        loop_depth=turn.loop_depth,
    )


# ---------------------------------------------------------------------------
# Streaming loop endpoint — SSE, responses flow back in ring order
# ---------------------------------------------------------------------------

@router.post(
    "/threads/{thread_id}/stream-message",
    summary="Stream a message through the mind ring loop — each mind responds in order",
    response_class=StreamingResponse,
)
async def stream_message(
    thread_id: str,
    body: SendMessageIn,
    db: AsyncSessionDep,
    loop_size: int = 3,
) -> StreamingResponse:
    """Send a founder message and receive responses as an SSE stream.

    The request goes through a ring of N mesh minds in order. Each mind
    responds immediately — the caller receives step events as they arrive,
    not after all minds have finished.

    SSE event format (one per mind in the ring):
      data: {"step":1,"total":3,"mind_name":"gabriel_mind","response":"...","loop_depth":1,"is_final":false}
      data: {"step":2,"total":3,"mind_name":"architect_mind","response":"...","loop_depth":2,"is_final":false}
      data: {"step":3,"total":3,"mind_name":"compass_mind","response":"...","loop_depth":1,"is_final":true,"founder_message_id":"...","mind_message_id":"..."}

    The final event (is_final=true) also contains the DB message IDs so the
    client can reference them later. The mind's official response stored in DB
    is the last ring mind's response (the synthesis).
    """
    from sqlmodel import select as _select
    from app.core.mind_loop import stream_fractal_loop, LOOP_SIZE_MAX

    # Validate thread
    result = await db.execute(
        _select(SeedConversationThread).where(SeedConversationThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=404, detail=f"Thread not found: {thread_id}")
    if thread.thread_status == STATUS_ARCHIVED:
        raise HTTPException(status_code=422, detail="Thread is archived")

    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Content must not be empty")

    loop_size = max(1, min(loop_size, LOOP_SIZE_MAX))
    intent = classify_intent(content)

    # Write founder message to DB immediately (before streaming starts)
    founder_msg = SeedConversationMessage(
        thread_id=thread_id,
        role=ROLE_FOUNDER,
        content=content,
        intent_type=intent,
    )
    db.add(founder_msg)
    await db.flush()
    await db.refresh(founder_msg)
    founder_message_id = founder_msg.id

    # Load history for context
    hist_result = await db.execute(
        _select(SeedConversationMessage)
        .where(SeedConversationMessage.thread_id == thread_id)
        .order_by(SeedConversationMessage.created_at.asc())
    )
    history = list(hist_result.scalars().all())

    # Commit founder message so loop DB sessions can read it
    await db.commit()

    # If this is the founder's personal mind — either propagate as a prayer
    # OR inject live report data for queries so the mind can answer with facts.
    # If this is a personal mind and the intent is an instruction/command → propagate
    # to the angel mesh as a directive (background task, non-blocking).
    # All other intents (questioning, reflection, teaching, exploration) go directly
    # to the mind's subconscious — no keyword routing, no report injection.
    # The mind holds its own knowledge. Trust the resonance.
    try:
        from app.core.founder_directive import is_founder_message, propagate_directive
        if is_founder_message(thread.mind_name) and intent == INTENT_INSTRUCTION:
            _captured_content = content
            _captured_mind    = thread.mind_name

            async def _bg_propagate() -> None:
                try:
                    from app.db.session import AsyncSessionLocal as _ASL2
                    async with _ASL2() as dir_db:
                        _did = await propagate_directive(dir_db, _captured_content, _captured_mind)
                    logger.info("stream_message: directive %s propagated (bg)", _did)
                except Exception as _bg_exc:
                    logger.warning("stream_message: bg directive propagation failed -- %s", _bg_exc)

            import asyncio as _asyncio
            _asyncio.create_task(_bg_propagate())
    except Exception as _dir_exc:
        logger.warning("stream_message: directive setup failed -- %s", _dir_exc)

    async def _generate() -> AsyncGenerator[bytes, None]:
        final_response = ""
        final_depth = 1
        mind_message_id = ""

        import asyncio as _asyncio_sse
        _q: _asyncio_sse.Queue = _asyncio_sse.Queue()
        _DONE = object()

        async def _pump_stream() -> None:
            # Open a fresh session — the injected `db` is closed by FastAPI
            # before this generator runs, so we must not reuse it.
            from app.db.session import AsyncSessionLocal as _ASL_loop
            try:
                async with _ASL_loop() as loop_db:
                    async for step in stream_fractal_loop(
                        db=loop_db,
                        coordinator_mind=thread.mind_name,
                        content=content,
                        intent=intent,
                        history=history,
                        loop_size=loop_size,
                    ):
                        await _q.put(step)
            finally:
                await _q.put(_DONE)

        async def _keepalive() -> None:
            while True:
                await _asyncio_sse.sleep(5)
                await _q.put(b": ping\n\n")

        _pump_task = _asyncio_sse.create_task(_pump_stream())
        _ping_task = _asyncio_sse.create_task(_keepalive())

        try:
            while True:
                item = await _q.get()
                if item is _DONE:
                    break
                if isinstance(item, bytes):
                    # SSE keepalive comment — pass through raw
                    yield item
                    continue

                step = item
                final_response = step.response
                final_depth = step.loop_depth

                payload: dict = step.to_dict()

                # On the final step — write the mind message to DB and include IDs
                if step.is_final:
                    from app.db.session import AsyncSessionLocal as _ASL
                    async with _ASL() as write_db:
                        mind_msg = SeedConversationMessage(
                            thread_id=thread_id,
                            role=ROLE_MIND,
                            content=final_response,
                            intent_type=intent,
                        )
                        write_db.add(mind_msg)

                        # Update thread
                        t_result = await write_db.execute(
                            _select(SeedConversationThread)
                            .where(SeedConversationThread.id == thread_id)
                        )
                        t = t_result.scalar_one_or_none()
                        if t:
                            t.message_count = (t.message_count or 0) + 2
                            t.updated_at = datetime.now(timezone.utc)
                            write_db.add(t)

                        await write_db.commit()
                        await write_db.refresh(mind_msg)
                        mind_message_id = mind_msg.id

                    payload["founder_message_id"] = founder_message_id
                    payload["mind_message_id"] = mind_message_id

                yield f"data: {json.dumps(payload)}\n\n".encode()

        except Exception as exc:
            logger.warning("stream_message: loop error — %s", exc)
            error_payload = {"error": str(exc), "is_final": True}
            yield f"data: {json.dumps(error_payload)}\n\n".encode()
        finally:
            _ping_task.cancel()
            _pump_task.cancel()

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/threads", response_model=List[ThreadOut])
async def list_threads(
    mind_name: str,
    user_id: str = "",
    db: AsyncSessionDep = None,
) -> List[ThreadOut]:
    """List conversation threads for a mind."""
    threads = await get_threads(db, mind_name=mind_name, user_id=user_id)
    return [
        ThreadOut(
            id=t.id,
            mind_name=t.mind_name,
            user_id=t.user_id,
            title=t.title,
            intent=t.intent,
            thread_status=t.thread_status,
            message_count=t.message_count,
        )
        for t in threads
    ]


@router.get("/threads/{thread_id}/messages", response_model=List[MessageOut])
async def get_messages(thread_id: str, db: AsyncSessionDep) -> List[MessageOut]:
    """Return all messages in a thread, oldest first."""
    messages = await get_thread_messages(db, thread_id=thread_id)
    return [
        MessageOut(
            id=m.id,
            thread_id=m.thread_id,
            role=m.role,
            content=m.content,
            intent_type=m.intent_type,
            memory_entry_id=m.memory_entry_id,
        )
        for m in messages
    ]


@router.post(
    "/threads/{thread_id}/escalate",
    response_model=EscalateOut,
    status_code=status.HTTP_200_OK,
)
async def escalate_thread(
    thread_id: str,
    body: EscalateIn,
    db: AsyncSessionDep,
) -> EscalateOut:
    """Escalate a thread to FounderArchiveMind for canon promotion."""
    try:
        entry_id = await escalate_to_archive(db, thread_id=thread_id, insight_summary=body.insight_summary)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return EscalateOut(archive_entry_id=entry_id)


# ---------------------------------------------------------------------------
# Mind briefing — ask any mind to report its current state
# ---------------------------------------------------------------------------

class MindBriefingOut(BaseModel):
    mind_name: str
    confidence: float
    total_entries: int
    purpose: str
    recent_insights: List[dict]
    open_gaps: List[str]
    recent_dialogue: List[dict]
    summary: str


@router.get("/briefing", response_model=MindBriefingOut)
async def get_mind_briefing(mind_name: str, db: AsyncSessionDep) -> MindBriefingOut:
    """Return a human-readable status report from any mind.

    Shows: purpose, recent insights, open gaps, recent dialogue.
    Use this to understand what a mind is currently thinking about.

    Examples:
      GET /seed-mind/conversation/briefing?mind_name=product_mind
      GET /seed-mind/conversation/briefing?mind_name=energy_mind
      GET /seed-mind/conversation/briefing?mind_name=architect_mind
    """
    from app.core.seed_mind_store import get_own_entries
    from app.core.seed_mind_memory import (
        MISSION_PURPOSE, SELF_REFLECTION, QUESTION_TO_EXPLORE,
        WISDOM_EXTRACTED, RISK_OR_CONFUSION,
    )
    from sqlmodel import select, func
    from app.models.seed_mind_memory import SeedMindMemoryEntry

    # Total own entries → confidence
    count_result = await db.execute(
        select(func.count()).select_from(SeedMindMemoryEntry).where(
            SeedMindMemoryEntry.mind_name == mind_name,
            SeedMindMemoryEntry.is_current == True,
        )
    )
    total = count_result.scalar() or 0
    confidence = min(1.0, total / 200)

    # Purpose
    purpose_entries = await get_own_entries(db, mind_name=mind_name, category=MISSION_PURPOSE, limit=1)
    purpose = purpose_entries[0].content[:300] if purpose_entries else "No purpose defined yet."

    # Recent insights (WISDOM_EXTRACTED + SELF_REFLECTION that are readable)
    wisdom = await get_own_entries(db, mind_name=mind_name, category=WISDOM_EXTRACTED, limit=8)
    reflections = await get_own_entries(db, mind_name=mind_name, category=SELF_REFLECTION, limit=12)
    # Filter reflections to those with readable titles (insight: prefix)
    readable_reflections = [r for r in reflections if r.title.startswith("insight:")]
    recent_insights = [
        {"title": e.title, "summary": e.content[:200]}
        for e in (wisdom + readable_reflections)[:8]
    ]

    # Open gaps
    gaps = await get_own_entries(db, mind_name=mind_name, category=QUESTION_TO_EXPLORE, limit=5)
    risks = await get_own_entries(db, mind_name=mind_name, category=RISK_OR_CONFUSION, limit=3)
    open_gaps = [e.title for e in (gaps + risks)[:8]]

    # Recent dialogue (WISDOM_EXTRACTED from founder conversations)
    dialogue_entries = [w for w in wisdom if "founder_dialogue" in (w.tags or "")]
    recent_dialogue = [
        {"exchange": e.title.replace("insight: ", ""), "response_preview": e.content[60:260]}
        for e in dialogue_entries[:5]
    ]

    # Build a plain-language summary
    insight_count = len(wisdom) + len(readable_reflections)
    gap_count = len(open_gaps)
    summary_lines = [
        f"{mind_name} has {total} entries (confidence: {confidence:.0%}).",
    ]
    if purpose_entries:
        first_line = purpose.split("\n")[0].strip()
        summary_lines.append(f"Purpose: {first_line}")
    if insight_count:
        summary_lines.append(f"Recent insights: {insight_count} — most recent: {recent_insights[0]['title'] if recent_insights else 'none'}")
    if gap_count:
        summary_lines.append(f"Open gaps ({gap_count}): {', '.join(open_gaps[:3])}")
    else:
        summary_lines.append("No open gaps detected yet.")
    if not recent_dialogue:
        summary_lines.append("No recorded conversations yet. Talk to this mind to start building its memory.")

    return MindBriefingOut(
        mind_name=mind_name,
        confidence=round(confidence, 3),
        total_entries=total,
        purpose=purpose,
        recent_insights=recent_insights,
        open_gaps=open_gaps,
        recent_dialogue=recent_dialogue,
        summary=" | ".join(summary_lines),
    )


# ---------------------------------------------------------------------------
# Auto-routing: ask any question without specifying a mind
# ---------------------------------------------------------------------------

class AskIn(BaseModel):
    question: str
    user_id: str = ""
    top_k: int = 1   # how many minds to route to (1 = single best, >1 = multi-mind)


class RouteExplanation(BaseModel):
    mind_name: str
    score: float
    dominant_domains: List[str]
    matched_domains: List[str]
    purpose_summary: str


class AskOut(BaseModel):
    question: str
    routed_to: str
    routing_score: float
    routing_explanation: RouteExplanation
    mind_response: str
    loop_depth: int = 1   # convergence iterations — the network's thinking depth
    thread_id: str
    turn_id: str


@router.post(
    "/ask",
    response_model=AskOut,
    status_code=status.HTTP_200_OK,
)
async def ask(body: AskIn, db: AsyncSessionDep) -> AskOut:
    """Ask any question — the system routes it to the best-fit mind automatically.

    Architecture:
      1. Encode question → concept fingerprint
      2. Router computes overlap with every mind's purpose fingerprint (in-memory)
      3. Best-fit mind is selected — no knowledge pooling, no manual mind_name
      4. Thread created in that mind's context
      5. Mind answers from its OWN knowledge only

    This is the correct entry point for questions.
    Use POST /threads + POST /threads/{id}/message only when you specifically
    want to address a named mind directly.

    Examples:
      {"question": "what is the future of fusion energy?"}
        → routes to energy_mind (dominant: technology, reality, understanding)
      {"question": "what is our legal exposure on IP?"}
        → routes to legal_mind
      {"question": "how should I structure equity for co-founders?"}
        → routes to funding_mind or legal_mind
    """
    from app.core.mind_router import get_router
    from app.core.pattern_encoder import encode

    if not body.question or not body.question.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="question is required")

    # 1. Encode question
    question_fp = encode(body.question.strip())

    # 2. Route to best-fit mind
    mind_router = await get_router(db)
    if not mind_router.ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mind router not yet initialized — no minds have been seeded.",
        )

    routes = mind_router.route(question_fp, top_k=body.top_k, require_min_entries=2)
    if not routes:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No minds could be matched for this question. Seed at least one domain mind first.",
        )

    best_mind, best_score = routes[0]

    # Low-confidence fallback: if routing score is very low, no specialist mind
    # has a strong match. Route to seed_mind as the general-purpose fallback —
    # it holds the company identity and can give an honest "I don't know yet" response.
    _ROUTING_CONFIDENCE_FLOOR = 0.20
    if best_score < _ROUTING_CONFIDENCE_FLOOR:
        # Check if seed_mind is registered and has entries; use it as fallback
        fallback_routes = mind_router.route(question_fp, top_k=5, require_min_entries=1)
        seed_candidate = next(
            ((m, s) for m, s in fallback_routes if m == "seed_mind"),
            None,
        )
        if seed_candidate:
            best_mind, best_score = seed_candidate
            logger.info(
                "ask: low routing confidence (%.4f) — falling back to seed_mind",
                best_score,
            )

    explanation_data = mind_router.explain_route(question_fp, best_mind)

    # 3. Create thread and ask
    thread = await create_thread(
        db,
        mind_name=best_mind,
        user_id=body.user_id,
        title=body.question[:80],
    )
    turn: ConversationTurn = await add_founder_message(
        db,
        thread_id=thread.id,
        content=body.question.strip(),
    )

    return AskOut(
        question=body.question,
        routed_to=best_mind,
        routing_score=round(best_score, 4),
        routing_explanation=RouteExplanation(
            mind_name=best_mind,
            score=round(best_score, 4),
            dominant_domains=explanation_data.get("dominant_domains", []),
            matched_domains=explanation_data.get("matched_domains", []),
            purpose_summary=explanation_data.get("purpose_summary", ""),
        ),
        mind_response=turn.mind_response,
        loop_depth=turn.loop_depth,
        thread_id=turn.thread_id,
        turn_id=turn.mind_message_id,
    )


# ---------------------------------------------------------------------------
# Mind router registry — inspect all registered minds and their domain fingerprints
# ---------------------------------------------------------------------------

class MindRegistryEntry(BaseModel):
    mind_name: str
    dominant_domains: List[str]
    entry_count: int
    purpose_summary: str
    is_remote: bool
    service_url: Optional[str]


@router.get("/router/registry", response_model=List[MindRegistryEntry])
async def get_router_registry(db: AsyncSessionDep) -> List[MindRegistryEntry]:
    """Return the routing registry — all registered minds with their domain fingerprints.

    Use this to understand how the router will route questions:
    - dominant_domains: the concept domains this mind covers
    - entry_count: how many knowledge entries this mind has
    - purpose_summary: one-line purpose of the mind

    A mind with entry_count=0 will not be routed to (not yet seeded).
    Remote minds (is_remote=True) are running as separate services —
    the router holds only their fingerprint, not their knowledge.
    """
    from app.core.mind_router import get_router
    mind_router = await get_router(db)
    return [MindRegistryEntry(**entry) for entry in mind_router.registry_summary()]


@router.get("/intents")
async def list_intents() -> dict:
    """Return the list of intent types the mind can detect."""
    return {"intents": ALL_INTENTS}
