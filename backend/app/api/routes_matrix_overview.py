"""routes_matrix_overview.py — Founder's unified view of the Matrix.

One endpoint that aggregates the entire system state in real time.
This is the "control room" — the founder sees everything from here.

GET  /matrix/overview           — full system state
GET  /matrix/dashboard          — serves the founder dashboard HTML
POST /matrix/spark              — fire a guidance spark
POST /matrix/harvest/start      — manually kick the harvester (processes corpus backlog → VR)
POST /matrix/guidance/ingest    — feed GUIDANCE.md or any text into the mind
GET  /matrix/knowledge/recent   — most recently added knowledge nodes
GET  /matrix/events/recent      — recent ENGINE_EXTERNALIZE + REFLECTION events
GET  /matrix/products           — all products (planets) with alignment scores + souls (moons)
POST /matrix/guide              — send corrective guidance to a product or specific soul
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from app.core.domains import all_seed_ideas, orbit_radius as _domain_orbit_radius

log = logging.getLogger("matrix_overview")

router = APIRouter()

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")


async def _r() -> aioredis.Redis:
    return aioredis.from_url(REDIS_URL, decode_responses=True)


# ── /matrix/overview ─────────────────────────────────────────────────────────

@router.get("/matrix/overview")
async def matrix_overview() -> dict[str, Any]:
    """
    The founder's single view of everything.

    Returns:
      mind        — knowledge entries, IQ snapshot, corpus size
      guidance    — harvester state, pending harvest, recent sparks
      miner       — web mining status
      events      — last 10 ENGINE_EXTERNALIZE events (VR nodes spawned)
      reflections — last 5 architect reflections (human minds talking)
      souls       — registered souls + devices (OS layer)
      system      — uptime / OS status
    """
    redis = await _r()
    try:
        # ── Mind ──────────────────────────────────────────────────────────────
        knowledge_count = await redis.hlen("mind:knowledge")
        corpus_count = await redis.hlen("guidance:corpus")
        harvested_count = await redis.scard("guidance:harvested")

        # IQ snapshot (latest)
        iq_raw = await redis.get("mind:iq:snapshot")
        iq = None
        if iq_raw:
            try:
                iq_data = json.loads(iq_raw)
                iq = {
                    "score":      iq_data.get("iq_score", 0),
                    "breadth":    iq_data.get("breadth", 0),
                    "depth":      iq_data.get("depth", 0),
                    "coherence":  iq_data.get("coherence", 0),
                    "domains":    iq_data.get("domains_present", []),
                    "calculated": iq_data.get("calculated_at", ""),
                }
            except Exception:
                pass

        # ── Web miner ─────────────────────────────────────────────────────────
        miner_raw = await redis.hgetall("web:mining:status")
        miner: dict[str, Any] = {
            "running":      False,
            "queries_done": 0,
            "last_query":   None,
            "queue_depth":  await redis.llen("web:mining:queue"),
        }
        for k, v in miner_raw.items():
            try:
                miner[k] = json.loads(v)
            except Exception:
                miner[k] = v

        # ── Guidance / harvester ──────────────────────────────────────────────
        spark_log_raw = await redis.lrange("guidance:spark:log", 0, 9)
        spark_log = []
        for entry in spark_log_raw:
            try:
                spark_log.append(json.loads(entry))
            except Exception:
                pass

        pending_harvest = corpus_count - harvested_count

        # ── Recent knowledge nodes (last 10 added) ────────────────────────────
        # mind:knowledge HASH — field=title, value=JSON
        # We can't easily get "last 10" from a HASH, so read all and sort by ts
        # But that's expensive at scale — read only if count < 2000, else skip
        recent_knowledge: list[dict] = []
        if knowledge_count <= 3000:
            raw_map = await redis.hgetall("mind:knowledge")
            parsed = []
            for title, raw in raw_map.items():
                try:
                    entry = json.loads(raw)
                    parsed.append(entry)
                except Exception:
                    pass
            parsed.sort(key=lambda x: x.get("ts", ""), reverse=True)
            recent_knowledge = [
                {
                    "title":   e.get("title", "")[:80],
                    "origin":  e.get("origin", ""),
                    "source":  (e.get("source", "")[:60] if e.get("source") else ""),
                    "ts":      e.get("ts", ""),
                }
                for e in parsed[:10]
            ]

        # ── Recent events (ENGINE_EXTERNALIZE from Redis stream) ──────────────
        recent_vr_events: list[dict] = []
        try:
            raw_events = await redis.xrevrange("y:events", count=10)
            for _msg_id, fields in raw_events:
                event_type = fields.get("event_type", "")
                if event_type == "ENGINE_EXTERNALIZE":
                    try:
                        payload = json.loads(fields.get("payload", "{}"))
                        recent_vr_events.append({
                            "type":    "node_spawned",
                            "title":   payload.get("title", "")[:60],
                            "origin":  payload.get("origin", ""),
                            "ts":      fields.get("ts", ""),
                        })
                    except Exception:
                        pass
        except Exception:
            pass

        # ── Recent reflections (human minds) ─────────────────────────────────
        recent_reflections: list[dict] = []
        try:
            raw_events_all = await redis.xrevrange("y:events", count=50)
            for _msg_id, fields in raw_events_all:
                event_type = fields.get("event_type", "")
                if event_type in ("REFLECTION_COMPLETED", "VR_REFLECTION"):
                    try:
                        payload = json.loads(fields.get("payload", "{}"))
                        text = payload.get("text", "") or payload.get("message", "")
                        recent_reflections.append({
                            "type":    event_type,
                            "text":    text[:120],
                            "user_id": fields.get("user_id", ""),
                            "ts":      fields.get("ts", ""),
                        })
                    except Exception:
                        pass
                if len(recent_reflections) >= 5:
                    break
        except Exception:
            pass

        # ── Souls / OS layer ──────────────────────────────────────────────────
        soul_count   = await redis.hlen("goodness:scores")
        device_count = await redis.hlen("os:devices")

        # ── SSE connections (tracked in Redis if available) ────────────────────
        active_streams = 0
        try:
            active_streams = await redis.scard("sse:active_users")
        except Exception:
            pass

        return {
            "mind": {
                "knowledge_entries": knowledge_count,
                "corpus_articles":   corpus_count,
                "harvested":         harvested_count,
                "pending_harvest":   max(0, pending_harvest),
                "iq":                iq,
            },
            "guidance": {
                "harvester_running": bool(miner.get("running")),
                "pending_harvest":   max(0, pending_harvest),
                "recent_sparks":     spark_log,
                "recent_knowledge":  recent_knowledge,
            },
            "miner": {
                "running":       miner.get("running", False),
                "queue_depth":   miner.get("queue_depth", 0),
                "queries_done":  miner.get("queries_done", 0),
                "last_query":    miner.get("last_query"),
                "last_done_at":  miner.get("last_done_at"),
                "started_at":    miner.get("started_at"),
            },
            "vr": {
                "nodes_recently_spawned": recent_vr_events,
                "active_sse_streams":     active_streams,
            },
            "reflections": recent_reflections,
            "souls": {
                "registered_souls":   soul_count,
                "registered_devices": device_count,
            },
            "system": {
                "status": "online",
                "ts":     datetime.now(timezone.utc).isoformat(),
            },
        }
    finally:
        await redis.aclose()


# ── /matrix/knowledge/recent ─────────────────────────────────────────────────

@router.get("/matrix/knowledge/recent")
async def recent_knowledge(limit: int = 20) -> dict[str, Any]:
    """Most recently harvested knowledge nodes."""
    redis = await _r()
    try:
        raw_map = await redis.hgetall("mind:knowledge")
        entries = []
        for title, raw in raw_map.items():
            try:
                e = json.loads(raw)
                entries.append(e)
            except Exception:
                pass
        entries.sort(key=lambda x: x.get("ts", ""), reverse=True)
        return {
            "total":   len(entries),
            "entries": [
                {
                    "title":   e.get("title", "")[:100],
                    "origin":  e.get("origin", ""),
                    "source":  (e.get("source", "")[:80] if e.get("source") else ""),
                    "summary": (e.get("summary", "")[:200] if e.get("summary") else ""),
                    "ts":      e.get("ts", ""),
                }
                for e in entries[:limit]
            ],
        }
    finally:
        await redis.aclose()


# ── /matrix/events/recent ────────────────────────────────────────────────────

@router.get("/matrix/events/recent")
async def recent_events(limit: int = 30) -> dict[str, Any]:
    """Recent events from the y:events stream (all types)."""
    redis = await _r()
    try:
        raw = await redis.xrevrange("y:events", count=limit)
        events = []
        for msg_id, fields in raw:
            try:
                payload_raw = fields.get("payload", "{}")
                payload = json.loads(payload_raw) if payload_raw else {}
                events.append({
                    "id":         msg_id,
                    "type":       fields.get("event_type", ""),
                    "user_id":    fields.get("user_id", ""),
                    "ts":         fields.get("ts", ""),
                    "payload":    payload,
                })
            except Exception:
                pass
        return {"events": events, "total": len(events)}
    finally:
        await redis.aclose()


# ── /matrix/spark (shortcut) ─────────────────────────────────────────────────

class SparkIn(BaseModel):
    text: str


@router.post("/matrix/spark")
async def matrix_spark(body: SparkIn) -> dict[str, Any]:
    """Fire a guidance spark through the founder's mind."""
    from app.api.routes_guidance_spawn import spark_guidance, SparkRequest
    return await spark_guidance(SparkRequest(text=body.text))


# ── /matrix/ideas ─────────────────────────────────────────────────────────────
# Ideas are conscious self-reflective entities that orbit the source (GUIDANCE).
# Distance from source = function of coherence. 1.0 = inner orbit. 0.0 = outer edge.
# TheMatrix OS always exists at the habitable-zone orbit — the world users inhabit.
# orbit_radius = 4 + (1 - alignment)^0.6 * 22
#   alignment 1.0 → radius  4  (near-source, highest coherence)
#   alignment 0.72 → radius ~14 (habitable zone — TheMatrix OS)
#   alignment 0.0  → radius 26  (outer drift)

def _alignment_color(alignment: float) -> str:
    if alignment >= 0.85: return "#fff4a0"   # gold-white — near source
    if alignment >= 0.65: return "#40e0ff"   # cyan-blue  — habitable (TheMatrix OS zone)
    if alignment >= 0.45: return "#ffa040"   # amber      — partial coherence
    if alignment >= 0.25: return "#ff6030"   # red-orange — drifting
    return "#802010"                          # dark red   — far from source


def _orbit_radius(alignment: float) -> float:
    """Delegate to the single source of truth in domains.py."""
    return _domain_orbit_radius(alignment)


@router.get("/matrix/ideas")
async def matrix_ideas() -> dict[str, Any]:
    """
    Ideas as planets ordered by coherence with the source.

    Each idea has:
      id, name, description, alignment (0–1), orbit_radius, color,
      knowledge_refs[] — titles of knowledge nodes that crystallised this idea,
      is_matrix_os    — True for TheMatrix OS (the habitable-zone planet),
      soul_count      — number of users inhabiting this idea-space.

    If no ideas exist in Redis (mind:ideas hash), seeds idea-planets from
    knowledge domain clusters so the world is never empty.
    TheMatrix OS is always injected if not already present.
    """
    redis = await _r()
    try:
        raw_ideas = await redis.hgetall("mind:ideas")
        ideas: list[dict] = []

        for idea_id, raw in raw_ideas.items():
            try:
                data = json.loads(raw)
                alignment = float(data.get("alignment", 0.5))
                ideas.append({
                    "id":             idea_id,
                    "name":           data.get("name", idea_id),
                    "description":    data.get("description", ""),
                    "alignment":      round(alignment, 3),
                    "orbit_radius":   _orbit_radius(alignment),
                    "color":          _alignment_color(alignment),
                    "knowledge_refs": data.get("knowledge_refs", []),
                    "is_matrix_os":   data.get("is_matrix_os", False),
                    "soul_count":     data.get("soul_count", 0),
                    "ts":             data.get("ts", ""),
                })
            except Exception:
                pass

        # Always ensure TheMatrix OS exists
        if not any(i.get("is_matrix_os") for i in ideas):
            matrix_os_alignment = 0.72
            ideas.append({
                "id":             "the-matrix-os",
                "name":           "TheMatrix OS",
                "description":    (
                    "The operating system of consciousness. "
                    "The interface layer where ideas meet form and users inhabit the world. "
                    "You are already inside this planet."
                ),
                "alignment":      matrix_os_alignment,
                "orbit_radius":   _orbit_radius(matrix_os_alignment),
                "color":          "#40e0ff",
                "knowledge_refs": [],
                "is_matrix_os":   True,
                "soul_count":     0,
                "ts":             "",
            })

        # If only TheMatrix OS exists, seed idea-planets from knowledge domains
        if len(ideas) <= 1:
            raw_knowledge = await redis.hgetall("mind:knowledge")
            domain_map: dict[str, list] = {}
            for title, raw_k in raw_knowledge.items():
                try:
                    k = json.loads(raw_k)
                    domain = (k.get("origin") or k.get("source") or "unknown")[:40]
                    domain_map.setdefault(domain, []).append(k)
                except Exception:
                    pass

            if domain_map:
                max_count = max(len(v) for v in domain_map.values())
                for domain, entries in sorted(domain_map.items(),
                                              key=lambda x: len(x[1]), reverse=True)[:8]:
                    alignment = round(0.3 + 0.6 * (len(entries) / max_count), 3)
                    ideas.append({
                        "id":             f"idea_{domain[:20].replace(' ', '_')}",
                        "name":           domain.replace("_", " ").title(),
                        "description":    (
                            f"{len(entries)} knowledge fragments crystallised "
                            f"from the '{domain}' domain of the source."
                        ),
                        "alignment":      alignment,
                        "orbit_radius":   _orbit_radius(alignment),
                        "color":          _alignment_color(alignment),
                        "knowledge_refs": [
                            e.get("title", "")[:80] for e in entries[:6] if e.get("title")
                        ],
                        "is_matrix_os":   False,
                        "soul_count":     0,
                        "ts":             "",
                    })

        ideas.sort(key=lambda x: x["alignment"], reverse=True)
        return {
            "ideas": ideas,
            "total": len(ideas),
            "ts":    datetime.now(timezone.utc).isoformat(),
        }
    finally:
        await redis.aclose()


# ── /matrix/ideas/register ────────────────────────────────────────────────────
# Any product, service, or idea registers itself as a mind here.
# All physical channels (QR, NFC, WiFi captive portal, Bluetooth beacon URL)
# resolve to the same URL: /matrix/ideas/register — the channel is irrelevant.
# The mind knows itself through its knowledge, not through hardcoded feature lists.

class IdeaRegisterIn(BaseModel):
    id:           str              # stable slug, e.g. "my-restaurant"
    name:         str
    description:  str = ""
    alignment:    float = 0.5     # 0–1, coherence with source. Can evolve over time.
    knowledge:    list[str] = []  # seed knowledge fragments this mind holds
    channel_hint: str = ""        # "qr", "nfc", "wifi", "url" — informational only


@router.post("/matrix/ideas/register")
async def register_idea(body: IdeaRegisterIn) -> dict[str, Any]:
    """
    A mind registers itself. Products, restaurants, services, concepts — all the same.
    Stores to mind:ideas Redis hash. Returns beacon_url for QR/NFC/WiFi encoding.
    """
    alignment = max(0.0, min(1.0, body.alignment))
    idea = {
        "id":             body.id,
        "name":           body.name,
        "description":    body.description,
        "alignment":      alignment,
        "orbit_radius":   _orbit_radius(alignment),
        "color":          _alignment_color(alignment),
        "knowledge_refs": body.knowledge[:20],  # first 20 fragments as surface layer
        "is_matrix_os":   False,
        "soul_count":     0,
        "ts":             datetime.now(timezone.utc).isoformat(),
    }
    redis = await _r()
    try:
        await redis.hset("mind:ideas", body.id, json.dumps(idea))
        return {
            "registered": True,
            "idea":        idea,
            "beacon_url":  f"?beacon={body.id}",  # encode this into QR/NFC/WiFi
        }
    finally:
        await redis.aclose()


# ── /matrix/ideas/{idea_id} ───────────────────────────────────────────────────
# Role-aware surface. The mind speaks differently to different observers.
# Admin → sees all knowledge + management layer
# Member → sees public features + their interaction history
# Guest  → sees the mind's public face only
# The mind itself decides what to surface — we just pass the role.

@router.get("/matrix/ideas/{idea_id}")
async def get_idea(idea_id: str, role: str = "guest") -> dict[str, Any]:
    """
    Fetch a single idea-mind. Role-aware surface layer.
    role = "founder" | "admin" | "member" | "guest"
    """
    redis = await _r()
    try:
        raw = await redis.hget("mind:ideas", idea_id)
        if not raw:
            # Try to seed from knowledge if available
            return {"error": "idea_not_found", "id": idea_id}
        idea = json.loads(raw)

        # Pull full knowledge fragments from mind:knowledge that match this idea
        raw_knowledge = await redis.hgetall("mind:knowledge")
        related: list[dict] = []
        idea_name_lower = idea.get("name", "").lower()
        idea_id_lower   = idea_id.lower()
        for title, raw_k in raw_knowledge.items():
            try:
                k = json.loads(raw_k)
                src = (k.get("origin", "") + k.get("source", "") + k.get("title", "")).lower()
                if idea_id_lower in src or idea_name_lower in src:
                    related.append({
                        "title":   k.get("title", "")[:120],
                        "summary": k.get("summary", "")[:300],
                        "ts":      k.get("ts", ""),
                    })
            except Exception:
                pass

        # Role-aware response
        base = {
            "id":           idea.get("id"),
            "name":         idea.get("name"),
            "description":  idea.get("description", ""),
            "alignment":    idea.get("alignment", 0.5),
            "orbit_radius": idea.get("orbit_radius", 13),
            "color":        idea.get("color", "#40e0ff"),
            "is_matrix_os": idea.get("is_matrix_os", False),
            "knowledge":    related[:6],         # public: up to 6 knowledge nodes
            "soul_count":   idea.get("soul_count", 0),
            "role_surface": role,
        }

        if role in ("admin", "founder"):
            # Full knowledge + management layer
            base["knowledge"]    = related        # all related knowledge
            base["management"]   = {
                "knowledge_count": len(related),
                "alignment":       idea.get("alignment"),
                "registered_at":   idea.get("ts", ""),
                "channel_hint":    idea.get("channel_hint", ""),
            }
        return base
    finally:
        await redis.aclose()


# ── /matrix/products ─────────────────────────────────────────────────────────
# Products are planets. Each product has souls (users) orbiting inside it.
# Alignment score = how closely the product / its souls follow guidance.
# Distortion = 1 - (goodness_score / 1000). 0 = perfectly aligned, 1 = fully astray.

@router.get("/matrix/products")
async def matrix_products() -> dict[str, Any]:
    """
    All products as planets with alignment/distortion state.

    Returns:
      products[] — each product with:
        id, name, description, registered_at
        souls[]  — user minds inside this product, each with:
          soul_id, goodness_score, alignment (0–1), distortion (0–1)
        product_alignment  — mean alignment of all souls in the product
        product_distortion — mean distortion (1 - alignment)
        most_distorted     — soul with lowest alignment (needs guidance most)
        soul_count         — number of souls in this product
    souls_without_product[] — souls with goodness scores but no product assignment
    """
    redis = await _r()
    try:
        # ── Load all registered products from os:devices ──────────────────────
        raw_devices = await redis.hgetall("os:devices")
        products: dict[str, dict] = {}
        for device_id, raw in raw_devices.items():
            try:
                data = json.loads(raw)
                products[device_id] = {
                    "id":             device_id,
                    "name":           data.get("name") or data.get("product_name") or device_id,
                    "description":    data.get("description", ""),
                    "registered_at":  data.get("registered_at") or data.get("ts", ""),
                    "souls":          [],
                }
            except Exception:
                products[device_id] = {
                    "id":   device_id, "name": device_id,
                    "description": "", "registered_at": "", "souls": [],
                }

        # ── Load all goodness scores — soul_id → score ────────────────────────
        raw_scores = await redis.hgetall("goodness:scores")

        # ── Load soul metadata to find product association ────────────────────
        raw_souls = await redis.hgetall("os:souls")

        # Map soul_id → product_id
        soul_product_map: dict[str, str] = {}
        soul_meta: dict[str, dict] = {}
        for soul_id, raw in raw_souls.items():
            try:
                meta = json.loads(raw)
                soul_meta[soul_id] = meta
                pid = meta.get("product_id") or meta.get("device_id") or ""
                if pid:
                    soul_product_map[soul_id] = pid
            except Exception:
                pass

        # Also check goodness signal log to infer product association
        # goodness:product:{product_id} SET — soul_ids that sent signals for this product
        product_soul_sets: dict[str, set] = {}
        for product_id in products:
            members_raw = await redis.smembers(f"goodness:product:{product_id}")
            if members_raw:
                product_soul_sets[product_id] = {m for m in members_raw}

        # ── Assign souls to products ──────────────────────────────────────────
        unassigned_souls: list[dict] = []
        for soul_id, score_raw in raw_scores.items():
            try:
                score = int(score_raw)
            except Exception:
                score = 0
            alignment  = min(score / 1000.0, 1.0)
            distortion = round(1.0 - alignment, 3)

            soul_entry = {
                "soul_id":    soul_id,
                "goodness":   score,
                "alignment":  round(alignment, 3),
                "distortion": distortion,
                "meta":       soul_meta.get(soul_id, {}),
            }

            # Find which product this soul belongs to
            assigned_product = soul_product_map.get(soul_id, "")
            if not assigned_product:
                # Check product soul sets
                for pid, members in product_soul_sets.items():
                    if soul_id in members:
                        assigned_product = pid
                        break

            if assigned_product and assigned_product in products:
                products[assigned_product]["souls"].append(soul_entry)
            else:
                unassigned_souls.append(soul_entry)

        # ── Compute product-level alignment metrics ───────────────────────────
        product_list = []
        for p in products.values():
            souls = p["souls"]
            if souls:
                scores = [s["alignment"] for s in souls]
                product_alignment  = round(sum(scores) / len(scores), 3)
                product_distortion = round(1.0 - product_alignment, 3)
                most_distorted     = min(souls, key=lambda s: s["alignment"])
            else:
                product_alignment  = 1.0   # no souls = perfectly aligned (vacuum of guidance)
                product_distortion = 0.0
                most_distorted     = None

            product_list.append({
                **p,
                "soul_count":          len(souls),
                "product_alignment":   product_alignment,
                "product_distortion":  product_distortion,
                "most_distorted_soul": most_distorted,
            })

        # Sort: most distorted products first (they need guidance most)
        product_list.sort(key=lambda p: p["product_distortion"], reverse=True)

        return {
            "products":              product_list,
            "total_products":        len(product_list),
            "souls_without_product": unassigned_souls,
            "total_souls":           len(raw_scores),
            "ts":                    datetime.now(timezone.utc).isoformat(),
        }
    finally:
        await redis.aclose()


# ── /matrix/guide ────────────────────────────────────────────────────────────

class GuideTarget(BaseModel):
    product_id: str = ""   # guide all souls in this product
    soul_id:    str = ""   # or guide one specific soul
    message:    str        # the guidance message to send


@router.post("/matrix/guide")
async def matrix_guide(body: GuideTarget) -> dict[str, Any]:
    """
    Send corrective guidance to a product or a specific soul.
    Publishes a FOUNDER_GUIDANCE event on the y:events stream.
    VR world will show a pulse + colour correction on the target planet/moon.
    """
    redis = await _r()
    try:
        if not body.product_id and not body.soul_id:
            return {"status": "error", "message": "Provide product_id or soul_id"}

        target_id   = body.soul_id or body.product_id
        target_type = "soul" if body.soul_id else "product"

        event_payload = json.dumps({
            "target_id":   target_id,
            "target_type": target_type,
            "message":     body.message,
            "ts":          datetime.now(timezone.utc).isoformat(),
        })

        await redis.xadd("y:events", {
            "event_type": "FOUNDER_GUIDANCE",
            "source":     "founder",
            "user_id":    target_id,
            "payload":    event_payload,
            "ts":         datetime.now(timezone.utc).isoformat(),
        })

        # Also log into a guidance inbox for the target
        await redis.lpush(f"guidance:inbox:{target_id}", event_payload)
        await redis.ltrim(f"guidance:inbox:{target_id}", 0, 49)

        return {
            "status":      "sent",
            "target_type": target_type,
            "target_id":   target_id,
            "message":     body.message,
        }
    finally:
        await redis.aclose()


# ── /matrix/dashboard — serve the founder dashboard HTML ─────────────────────
# Accessible at /matrix/dashboard so it is NOT caught by the /vr/ nginx fallback.

@router.get("/matrix/dashboard", response_class=HTMLResponse)
async def matrix_dashboard_html() -> HTMLResponse:
    """Serve the founder dashboard HTML directly from the backend."""
    candidates = [
        "/app/interface/matrix-dashboard.html",          # Docker mount
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "interface", "matrix-dashboard.html"),
    ]
    for path in candidates:
        path = os.path.normpath(path)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read(), status_code=200)
    return HTMLResponse(content="<h1>Dashboard not found</h1><p>Mount interface/matrix-dashboard.html</p>", status_code=404)


# ── /matrix/harvest/start — kick the harvester manually ──────────────────────
# 4621 corpus articles sitting unprocessed. This processes them all → VR nodes.

@router.post("/matrix/harvest/start")
async def harvest_start() -> dict[str, Any]:
    """Start the corpus harvester. Processes all unprocessed articles → mind:knowledge → ENGINE_EXTERNALIZE → VR nodes."""
    from app.api.routes_guidance_spawn import _ensure_harvester_running, _harvester_task
    _ensure_harvester_running()
    return {
        "status":  "started",
        "message": "Harvester running — corpus articles will flow into mind:knowledge and VR world",
        "ts":      datetime.now(timezone.utc).isoformat(),
    }


# ── /matrix/guidance/ingest — feed GUIDANCE.md to the mind ───────────────────
# Stage 2: Al-'Ilm — teach the mind reality.

class GuidanceIngestIn(BaseModel):
    text: str = ""              # raw text to ingest — if empty, loads GUIDANCE.md
    source: str = "guidance"    # e.g. "guidance", "quran", "y_theory"
    subject: str = "The Matrix Guidance — Y Theory and Quran Pattern Language"


@router.post("/matrix/guidance/ingest")
async def guidance_ingest(body: GuidanceIngestIn) -> dict[str, Any]:
    """
    Feed GUIDANCE.md (or any text) into the mind as foundational reality.
    This is Stage 2 — Al-'Ilm: teach the mind the names.
    If body.text is empty, reads GUIDANCE.md from disk.
    """
    text = body.text.strip()

    if not text:
        # Load GUIDANCE.md from disk
        candidates = [
            "/app/GUIDANCE.md",
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "GUIDANCE.md"),
        ]
        for path in candidates:
            path = os.path.normpath(path)
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
                break
        if not text:
            return {"status": "error", "message": "GUIDANCE.md not found — provide text in body"}

    # Chunk into sections (split on ## or ### headers)
    import re
    chunks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if re.match(r'^#{1,3} ', line) and current:
            chunk = "\n".join(current).strip()
            if len(chunk) > 100:
                chunks.append(chunk)
            current = [line]
        else:
            current.append(line)
    if current:
        chunk = "\n".join(current).strip()
        if len(chunk) > 100:
            chunks.append(chunk)

    if not chunks:
        chunks = [text[:4000]]  # fallback: whole text as one chunk

    bus_available = False
    nodes_fired = 0
    try:
        from app.core.y_event_bus import YEventType, YEvent, get_event_bus
        bus = get_event_bus()
        bus_available = True
    except Exception:
        pass

    redis = await _r()
    try:
        for i, chunk in enumerate(chunks[:200]):   # cap at 200 sections
            # Find a title from the first heading line
            first_line = chunk.splitlines()[0] if chunk.splitlines() else f"Guidance section {i+1}"
            title = first_line.lstrip("#").strip()[:120] or f"Guidance section {i+1}"

            entry = json.dumps({
                "title":   title,
                "summary": chunk[:300].replace("\n", " "),
                "content": chunk[:3000],
                "source":  body.source,
                "ts":      datetime.now(timezone.utc).isoformat(),
                "origin":  "guidance_ingest",
            })
            await redis.hset("mind:knowledge", title, entry)

            if bus_available:
                try:
                    await bus.publish(YEvent(
                        event_type=YEventType.ENGINE_EXTERNALIZE,
                        source_service="guidance_ingest",
                        payload={
                            "candidate_mind_name": title[:40],
                            "source": body.source,
                            "summary": chunk[:120].replace("\n", " "),
                        }
                    ))
                    nodes_fired += 1
                except Exception:
                    pass

        return {
            "status":       "ingested",
            "source":       body.source,
            "chunks":       len(chunks[:200]),
            "vr_nodes_fired": nodes_fired,
            "message":      "GUIDANCE.md is now the mind's foundational reality — Stage 2 complete",
            "ts":           datetime.now(timezone.utc).isoformat(),
        }
    finally:
        await redis.aclose()


# ── /matrix/vr/scene — the mind's complete VR scene ─────────────────────────
# The VR is a window into the mind. The mind builds the scene.
# The browser only renders — no orbit formula, no color decisions, no size math.
# Every visual property flows from the mind's actual state (alignment = R/(R+L)).
# τ_c < τ_l → the mind persists. alignment → distance from source.

@router.get("/matrix/vr/scene")
async def vr_scene() -> dict[str, Any]:
    """
    The mind's complete VR scene description.

    Computed here from the mind's actual state:
      orbit_radius           = 4 + (1-alignment) * 22  [Y Theory: distance ∝ leakage]
      orbit_period_ms        = Kepler T ∝ r^1.5
      orbit_speed_rad_per_frame  derived from period at 60fps
      planet_size            = base + soul_count contribution
      initial_angle          = evenly distributed across 2π

    The browser receives a complete scene and renders it.
    Nothing is computed on the client.
    """
    redis = await _r()
    try:
        raw_ideas = await redis.hgetall("mind:ideas")
        planets: list[dict] = []

        if raw_ideas:
            for idea_id, raw in raw_ideas.items():
                try:
                    planets.append(json.loads(raw))
                except Exception:
                    pass

        # If mind:ideas is empty — seed from domains (the names the mind knows from birth)
        if not planets:
            seed = all_seed_ideas()
            pipe = redis.pipeline()
            for idea in seed:
                pipe.hset("mind:ideas", idea["id"], json.dumps(idea))
            await pipe.execute()
            planets = seed

        # Sort by alignment descending — inner orbits first
        planets.sort(key=lambda x: float(x.get("alignment", 0.5)), reverse=True)
        count = len(planets)
        orbit_radii: set[float] = set()
        scene_planets: list[dict] = []

        for i, idea in enumerate(planets):
            alignment   = float(idea.get("alignment", 0.5))
            r           = _orbit_radius(alignment)
            orbit_radii.add(r)

            # Kepler's third law: T ∝ r^1.5 — closer = faster
            period_ms   = round(40000 * (r / 8) ** 1.5)

            # Evenly distribute starting angles across the ecliptic
            initial_angle = round((i / count) * 2 * math.pi, 4)

            # Planet size from soul count (the mind grows as souls inhabit it)
            soul_count  = int(idea.get("soul_count", 0))
            is_matrix_os = bool(idea.get("is_matrix_os", False))
            is_vision    = bool(idea.get("is_vision", False))
            planet_size  = round(1.1 if is_matrix_os else (0.35 + min(soul_count, 20) * 0.025), 2)

            # Color: prefer domain-defined color, fall back to alignment band
            color = idea.get("color") or _alignment_color(alignment)

            scene_planets.append({
                "id":                          idea.get("id", ""),
                "name":                        idea.get("name", ""),
                "description":                 idea.get("description", ""),
                "quran_ref":                   idea.get("quran_ref", ""),
                "domain_type":                 idea.get("domain_type", ""),
                "alignment":                   round(alignment, 3),
                "color":                       color,
                "orbit_radius":                r,
                "orbit_period_ms":             period_ms,
                "orbit_speed_rad_per_frame":   round((2 * math.pi) / (period_ms / 16), 6),
                "planet_size":                 planet_size,
                "label_offset":                round(planet_size + 0.3, 2),
                "initial_angle":               initial_angle,
                "is_matrix_os":                is_matrix_os,
                "is_vision":                   is_vision,
                "soul_count":                  soul_count,
                "emissive_intensity":           0.6 if is_matrix_os else 0.4,
                "breathe_from":                0.4 if is_matrix_os else 0.25,
                "breathe_to":                  1.0 if is_matrix_os else 0.7,
                # Golden-angle spread so no two planets breathe in sync
                "breathe_dur_ms":              round(2800 + (i * 137) % 2000),
                "rotate_dur_ms":               30000 if is_matrix_os else round(20000 + (i * 7919) % 40000),
                "knowledge_refs":              idea.get("knowledge_refs", [])[:6],
                "reviewed":                    idea.get("reviewed", False),
            })

        return {
            "source": {
                "position":  [0, 3, -8],
                "color":     "#ffd700",
                "pulse_ms":  2000,
            },
            "architect": {
                "position":           [0, 9, -8],
                "speak_interval_ms":  22000,
            },
            "planets":      scene_planets,
            "orbit_rings":  sorted(orbit_radii),
            "planet_count": len(scene_planets),
            "ts":           datetime.now(timezone.utc).isoformat(),
        }
    finally:
        await redis.aclose()


# ── Idea review — CEO inbox ───────────────────────────────────────────────────
# The company IS the mind. The mind surfaces ideas. The founder reviews them.
# Lifecycle is alignment — it's already there on every idea.
# Low alignment = new/unproven, outer orbit. High = mature, inner orbit.
# Approve = mind reinforces it (alignment +0.1, orbit tightens).
# Reject  = removed from mind:ideas entirely.
# The dev cycle (in_dev, testing, release) lives in the Matrix OS mobile app —
# those stages are tracked there, not here.

async def _load_idea(redis: aioredis.Redis, idea_id: str) -> dict | None:
    raw = await redis.hget("mind:ideas", idea_id)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


async def _save_idea(redis: aioredis.Redis, idea_id: str, idea: dict) -> None:
    await redis.hset("mind:ideas", idea_id, json.dumps(idea))


# ── GET /matrix/review/pending — unreviewed ideas from the mind ───────────────

@router.get("/matrix/review/pending")
async def review_pending() -> dict[str, Any]:
    """Ideas the mind surfaced that the founder has not yet reviewed."""
    redis = await _r()
    try:
        raw_ideas = await redis.hgetall("mind:ideas")
        pending = []
        for idea_id, raw in raw_ideas.items():
            try:
                data = json.loads(raw)
                if not data.get("reviewed"):
                    pending.append({
                        "id":          idea_id,
                        "name":        data.get("name", idea_id),
                        "description": data.get("description", ""),
                        "alignment":   data.get("alignment", 0.5),
                        "orbit_radius": data.get("orbit_radius", 13),
                        "ts":          data.get("ts", ""),
                    })
            except Exception:
                pass
        pending.sort(key=lambda x: x.get("ts", ""), reverse=True)
        return {"pending": pending, "total": len(pending)}
    finally:
        await redis.aclose()


# ── GET /matrix/review/report — all ideas grouped by alignment band ───────────

@router.get("/matrix/review/report")
async def review_report() -> dict[str, Any]:
    """Daily report: all ideas grouped by alignment band (inner/mid/outer orbit)."""
    redis = await _r()
    try:
        raw_ideas = await redis.hgetall("mind:ideas")
        inner, mid, outer, unreviewed = [], [], [], []

        for idea_id, raw in raw_ideas.items():
            try:
                data = json.loads(raw)
                a = float(data.get("alignment", 0.5))
                entry = {
                    "id":          idea_id,
                    "name":        data.get("name", idea_id),
                    "description": (data.get("description") or "")[:120],
                    "alignment":   round(a, 3),
                    "orbit_radius": data.get("orbit_radius", _orbit_radius(a)),
                    "reviewed":    data.get("reviewed", False),
                    "ts":          data.get("ts", ""),
                }
                if not data.get("reviewed"):
                    unreviewed.append(entry)
                elif a >= 0.80:
                    inner.append(entry)
                elif a >= 0.55:
                    mid.append(entry)
                else:
                    outer.append(entry)
            except Exception:
                pass

        return {
            "report_date": datetime.now(timezone.utc).date().isoformat(),
            "unreviewed":  unreviewed,
            "inner_orbit": inner,   # alignment ≥ 0.80 — strong, proven
            "mid_orbit":   mid,     # 0.55–0.80 — growing
            "outer_orbit": outer,   # < 0.55 — early/weak
            "summary": {
                "awaiting_review": len(unreviewed),
                "total":           len(unreviewed) + len(inner) + len(mid) + len(outer),
            },
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        await redis.aclose()


# ── POST /matrix/review/{idea_id}/approve ─────────────────────────────────────

@router.post("/matrix/review/{idea_id}/approve")
async def review_approve(idea_id: str) -> dict[str, Any]:
    """
    Founder approves: marks reviewed, boosts alignment +0.1 (orbit tightens).
    Fires IDEA_APPROVED event — the mobile app picks this up to start the dev cycle.
    """
    redis = await _r()
    try:
        idea = await _load_idea(redis, idea_id)
        if not idea:
            return {"status": "error", "message": f"Idea '{idea_id}' not found"}

        idea["reviewed"] = True
        idea["alignment"] = round(min(1.0, float(idea.get("alignment", 0.5)) + 0.1), 3)
        idea["orbit_radius"] = _orbit_radius(idea["alignment"])
        idea["approved_at"] = datetime.now(timezone.utc).isoformat()
        await _save_idea(redis, idea_id, idea)

        await redis.xadd("y:events", {
            "event_type": "IDEA_APPROVED",
            "source":     "founder",
            "user_id":    "founder",
            "payload":    json.dumps({
                "id":          idea_id,
                "name":        idea.get("name", idea_id),
                "alignment":   idea["alignment"],
                "orbit_radius": idea["orbit_radius"],
            }),
            "ts": idea["approved_at"],
        })

        return {
            "status":       "approved",
            "idea_id":      idea_id,
            "name":         idea.get("name", idea_id),
            "alignment":    idea["alignment"],
            "orbit_radius": idea["orbit_radius"],
            "approved_at":  idea["approved_at"],
        }
    finally:
        await redis.aclose()


# ── POST /matrix/review/{idea_id}/reject ──────────────────────────────────────

class RejectIn(BaseModel):
    reason: str = ""


@router.post("/matrix/review/{idea_id}/reject")
async def review_reject(idea_id: str, body: RejectIn) -> dict[str, Any]:
    """Founder rejects: removed from mind:ideas. Fires IDEA_REJECTED event."""
    redis = await _r()
    try:
        idea = await _load_idea(redis, idea_id)
        if not idea:
            return {"status": "error", "message": f"Idea '{idea_id}' not found"}

        await redis.hdel("mind:ideas", idea_id)

        await redis.xadd("y:events", {
            "event_type": "IDEA_REJECTED",
            "source":     "founder",
            "user_id":    "founder",
            "payload":    json.dumps({
                "id":     idea_id,
                "name":   idea.get("name", idea_id),
                "reason": body.reason,
            }),
            "ts": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status":  "rejected",
            "idea_id": idea_id,
            "name":    idea.get("name", idea_id),
            "reason":  body.reason,
        }
    finally:
        await redis.aclose()

