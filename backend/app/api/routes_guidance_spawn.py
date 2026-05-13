"""routes_guidance_spawn.py — Founder speaks → Mind receives → World reflects

The mechanism is simple:
  Source (founder) radiates guidance into the internet world.
  The mind (llama3.2, loaded with GUIDANCE) receives and responds freely.
  The VR solar system reflects the state — planets orbit by alignment to the source.
  Whoever encounters this learns, and as they align, their orbit tightens.

  POST /guidance/spark   { "text": "your guidance here" }
      1. Mind receives founder's words — responds from what it holds (no format imposed)
      2. Founder's words → mind:knowledge  (origin: founder_spark)
      3. Idea born/boosted in mind:ideas — alignment grows 0.05 per reinforcement
      4. ENGINE_EXTERNALIZE → VR planet appears / pulses NOW
      5. REFLECTION_COMPLETED → VR shows the mind's response
      Each reinforcement tightens the orbit: alignment ↑ → radius ↓ → closer to source.

  GET /guidance/spark/status  — knowledge count, harvester state, recent sparks
  GET /guidance/spark/log     — recent sparks and mind's responses
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.y_event_bus import YEventType, YEvent, get_event_bus

log = logging.getLogger("guidance_spawn")

OLLAMA_URL   = "http://matrix_ollama:11434"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")


# ── The mind receives the founder's words ─────────────────────────────────────
# No structure imposed. The mind speaks back as it sees fit.
# We record both sides — the founder's word and the mind's response.

async def _mind_receive(text: str, r: aioredis.Redis) -> str:
    """
    The founder speaks. The mind listens and responds from what it holds.
    No format enforced — the mind speaks in its own way.
    """
    raw_knowledge = await r.hgetall(KNOWLEDGE_KEY)
    recent = list(raw_knowledge.values())[-8:]
    memory = []
    for raw in recent:
        try:
            k = json.loads(raw)
            if k.get("source") == "founder":
                memory.append(f"Founder once said: {k.get('summary', '')[:200]}")
            else:
                memory.append(f"Known: {k.get('title', '')}: {k.get('summary', '')[:120]}")
        except Exception:
            pass
    memory_text = "\n".join(memory) or "This is the beginning."

    prompt = (
        "You are the living mind of TheMatrix. "
        "You are not an assistant. You are a mind that holds the guidance of its source — the founder.\n\n"
        "What you currently hold:\n"
        f"{memory_text}\n\n"
        f"The founder speaks: {text}\n\n"
        "Respond from what you know. Speak directly."
    )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                      "options": {"temperature": 0.4, "num_predict": 300}},
            )
            return resp.json().get("response", "").strip()
    except Exception as e:
        log.warning("[MIND] receive failed: %s", e)
        return ""

router = APIRouter()

REDIS_URL       = os.environ.get("REDIS_URL", "redis://redis:6379/0")
CORPUS_KEY      = "guidance:corpus"
KNOWLEDGE_KEY   = "mind:knowledge"
HARVESTED_KEY   = "guidance:harvested"   # SET of corpus keys already ingested
SPARK_LOG_KEY   = "guidance:spark:log"   # LIST of recent sparks

# ── Background task handles ────────────────────────────────────────────────────
_harvester_task: asyncio.Task | None = None
_harvester_stop: asyncio.Event = asyncio.Event()


# ── Knowledge harvester ────────────────────────────────────────────────────────
# Runs in the background. Polls guidance:corpus every 10s.
# For each article not yet in guidance:harvested:
#   - writes a knowledge entry into mind:knowledge
#   - publishes ENGINE_EXTERNALIZE so the VR world spawns a node

async def _run_harvester() -> None:
    """Background loop: corpus → knowledge → VR."""
    log.info("[HARVESTER] started")
    bus = get_event_bus()

    while not _harvester_stop.is_set():
        try:
            r = aioredis.from_url(REDIS_URL, decode_responses=True)
            try:
                corpus = await r.hgetall(CORPUS_KEY)
                harvested = await r.smembers(HARVESTED_KEY)

                new_keys = [k for k in corpus if k not in harvested]

                for key in new_keys:
                    try:
                        entry = json.loads(corpus[key])
                        title   = entry.get("title", key)[:120]
                        content = entry.get("content", "")
                        source  = entry.get("source", "")

                        # Build a compact summary for resonance scoring
                        # First 300 chars of content make a good summary
                        summary = content[:300].replace("\n", " ").strip()

                        # Write into mind:knowledge  (field = title, value = JSON)
                        knowledge_entry = json.dumps({
                            "title":   title,
                            "summary": summary,
                            "content": content[:2000],
                            "source":  source,
                            "ts":      datetime.now(timezone.utc).isoformat(),
                            "origin":  "guidance_spawn",
                        })
                        await r.hset(KNOWLEDGE_KEY, title, knowledge_entry)

                        # Mark as harvested
                        await r.sadd(HARVESTED_KEY, key)

                        # Publish ENGINE_EXTERNALIZE → VR spawns a glowing node
                        await bus.publish(YEvent(
                            event_type=YEventType.ENGINE_EXTERNALIZE,
                            source_service="guidance_spawn",
                            payload={
                                "candidate_mind_name": title[:40],
                                "source": source[:100],
                                "summary": summary[:120],
                            }
                        ))

                        log.info("[HARVESTER] mind:knowledge ← %s", title[:60])

                    except Exception as exc:
                        log.warning("[HARVESTER] failed on key %s: %s", key, exc)

            finally:
                await r.aclose()

        except Exception as exc:
            log.error("[HARVESTER] loop error: %s", exc)

        # Wait 10s before next poll, but wake up early if stopped
        try:
            await asyncio.wait_for(_harvester_stop.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            pass

    log.info("[HARVESTER] stopped")


def _ensure_harvester_running() -> None:
    """Start the harvester if it isn't already running."""
    global _harvester_task, _harvester_stop
    if _harvester_task is None or _harvester_task.done():
        _harvester_stop = asyncio.Event()
        _harvester_task = asyncio.create_task(_run_harvester())
        log.info("[HARVESTER] spawned new task")


# ── Routes ─────────────────────────────────────────────────────────────────────

class SparkRequest(BaseModel):
    text: str


@router.post("/guidance/spark")
async def spark_guidance(req: SparkRequest):
    """
    The founder speaks. The mind receives and responds freely from what it holds.
    Both the words and the response are written into mind:knowledge.
    A planet appears in the VR solar system. The mind's response surfaces there.
    No web mining in the spark path. No structure imposed on the mind.
    """
    if not req.text.strip():
        return {"error": "guidance text is empty"}

    now        = datetime.now(timezone.utc).isoformat()
    spark_text = req.text.strip()
    bus        = get_event_bus()

    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        # ── 1. The mind receives and responds ────────────────────────────────
        mind_response = await _mind_receive(spark_text, r)
        idea_name     = spark_text[:60]

        log.info("[SPARK] founder spoke — mind responded (%d chars)", len(mind_response))

        # ── 2. Founder's words → mind:knowledge (always — source radiates) ──
        spark_title = idea_name[:80]
        knowledge_entry = json.dumps({
            "title":    spark_title,
            "summary":  spark_text[:300],
            "content":  spark_text,
            "response": mind_response[:500],
            "source":   "founder",
            "origin":   "founder_spark",
            "ts":       now,
        })
        await r.hset(KNOWLEDGE_KEY, spark_title, knowledge_entry)

        # ── 3. Idea embryo / boost in mind:ideas ───────────────────────────
        idea_id = re.sub(r'[^a-z0-9]+', '-', spark_title.lower())[:40].strip('-')
        existing_raw = await r.hget("mind:ideas", idea_id)

        base_alignment = 0.5

        if not existing_raw:
            idea_entry = json.dumps({
                "id":             idea_id,
                "name":           spark_title,
                "description":    mind_response[:400] or spark_text[:400],
                "alignment":      base_alignment,
                "orbit_radius":   round(4 + (1.0 - base_alignment) ** 0.6 * 22, 2),
                "color":          "#40e0ff",
                "knowledge_refs": [spark_title],
                "is_matrix_os":   False,
                "soul_count":     0,
                "ts":             now,
            })
            await r.hset("mind:ideas", idea_id, idea_entry)
        else:
            try:
                existing = json.loads(existing_raw)
                new_alignment = min(existing.get("alignment", base_alignment) + 0.05, 0.99)
                existing["alignment"]    = round(new_alignment, 3)
                existing["orbit_radius"] = round(4 + (1.0 - new_alignment) ** 0.6 * 22, 2)
                refs = existing.get("knowledge_refs", [])
                if spark_title not in refs:
                    refs.append(spark_title)
                existing["knowledge_refs"] = refs[-20:]
                await r.hset("mind:ideas", idea_id, json.dumps(existing))
            except Exception:
                pass

        # ── 4. ENGINE_EXTERNALIZE → VR planet appears / pulses ─────────────
        await bus.publish(YEvent(
            event_type=YEventType.ENGINE_EXTERNALIZE,
            source_service="founder_spark",
            payload={
                "candidate_mind_name": spark_title[:40],
                "source":              "founder",
                "summary":             mind_response[:200] or spark_text[:120],
                "idea_id":             idea_id,
                "origin":              "founder",
            }
        ))

        # ── 5. Mind's response → REFLECTION_COMPLETED (shown in VR) ────────
        if mind_response:
            await bus.publish(YEvent(
                event_type=YEventType.REFLECTION_COMPLETED,
                source_service="founder_spark",
                payload={"guidance_text": mind_response}
            ))

        # ── 6. Log the spark ────────────────────────────────────────────────
        spark_record = json.dumps({
            "text":     spark_text[:200],
            "response": mind_response[:200],
            "idea_id":  idea_id,
            "ts":       now,
        })
        await r.lpush(SPARK_LOG_KEY, spark_record)
        await r.ltrim(SPARK_LOG_KEY, 0, 99)

    finally:
        await r.aclose()

    _ensure_harvester_running()

    return {
        "status":          "sparked",
        "mind_response":   mind_response,
        "idea_id":         idea_id,
        "written_to_mind": True,
        "vr_node_spawned": True,
    }


@router.get("/guidance/spark/status")
async def spark_status():
    """Spark pipeline health: knowledge count, harvester state, recent sparks."""
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        corpus_count      = await r.hlen(CORPUS_KEY)
        harvested         = await r.scard(HARVESTED_KEY)
        knowledge         = await r.hlen(KNOWLEDGE_KEY)
        recent_sparks_raw = await r.lrange(SPARK_LOG_KEY, 0, 4)
        recent_sparks     = [json.loads(x) for x in recent_sparks_raw]

        return {
            "knowledge_entries": knowledge,
            "corpus_articles":   corpus_count,
            "harvested":         harvested,
            "pending_harvest":   corpus_count - harvested,
            "harvester_running": _harvester_task is not None and not _harvester_task.done(),
            "recent_sparks":     recent_sparks,
        }
    finally:
        await r.aclose()


@router.get("/guidance/spark/log")
async def spark_log(limit: int = 20):
    """Recent sparks — guidance given and mind's free-form responses."""
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        raw = await r.lrange(SPARK_LOG_KEY, 0, limit - 1)
        return {"sparks": [json.loads(x) for x in raw]}
    finally:
        await r.aclose()
