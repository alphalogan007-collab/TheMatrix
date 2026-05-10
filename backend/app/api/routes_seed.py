"""routes_seed.py — Seed input entry point + read what the engine has learned.

POST /seed/input   — push raw input into the topology (seed:input stream)
GET  /seed/wisdom  — list all wisdom entries (filterable by angel / category)
GET  /seed/graph   — return node+edge data for the pattern graph
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import select

from app.db.redis_client import get_redis
from app.db.session import AsyncSessionDep
from app.models.seed_mind_memory import SeedMindMemoryEntry

router = APIRouter()


# == Input models =============================================================

class SeedInput(BaseModel):
    input_type: str = "text"   # text | video | audio
    content: str
    source: str = "user"
    session_id: str = ""


class SeedInputResponse(BaseModel):
    ok: bool
    session_id: str
    stream: str
    msg_id: str


# == POST /seed/input — push raw input into the topology ======================

@router.post("/seed/input", response_model=SeedInputResponse)
async def post_seed_input(
    body: SeedInput,
    redis=Depends(get_redis),
):
    """Push raw input into the topology via the seed:input Redis stream."""
    session_id = body.session_id or uuid.uuid4().hex
    msg_id = await redis.xadd(
        "seed:input",
        {
            "input_type": body.input_type,
            "content":    body.content,
            "source":     body.source,
            "session_id": session_id,
            "ts":         datetime.now(timezone.utc).isoformat(),
        },
    )
    return SeedInputResponse(
        ok=True,
        session_id=session_id,
        stream="seed:input",
        msg_id=msg_id,
    )



    id: str
    mind_name: str
    category: str
    title: str
    content: str
    claim_type: str
    tags: str


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    weight: int


class GraphEdge(BaseModel):
    source: str
    target: str
    strength: float


class GraphData(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


@router.get("/seed/wisdom")
async def get_wisdom(
    angel: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(50, le=500),
    db: AsyncSessionDep = None,
):
    """Return seed wisdom entries — what the engine has learned so far."""
    q = select(SeedMindMemoryEntry)
    if angel:
        q = q.where(SeedMindMemoryEntry.mind_name.contains(angel))
    if category:
        q = q.where(SeedMindMemoryEntry.category == category)
    q = q.limit(limit)
    result = await db.execute(q)
    entries = result.scalars().all()
    return [
        {
            "id": str(e.id),
            "mind_name": e.mind_name,
            "category": e.category,
            "title": e.title,
            "content": e.content[:300],
            "claim_type": e.claim_type,
            "tags": e.tags or "",
        }
        for e in entries
    ]


@router.get("/seed/graph", response_model=GraphData)
async def get_graph(db: AsyncSessionDep):
    """Return graph nodes + edges from seeded wisdom (sampled)."""
    q = select(SeedMindMemoryEntry).limit(500)
    result = await db.execute(q)
    entries = result.scalars().all()

    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    for e in entries:
        if e.mind_name not in nodes:
            nodes[e.mind_name] = GraphNode(
                id=e.mind_name, label=e.mind_name.replace("_mind", ""),
                type="angel", weight=0,
            )
        nodes[e.mind_name].weight += 1

        if e.category not in nodes:
            nodes[e.category] = GraphNode(
                id=e.category, label=e.category, type="category", weight=0,
            )
        nodes[e.category].weight += 1

        edges.append(GraphEdge(source=e.mind_name, target=e.category, strength=1.0))

    return GraphData(nodes=list(nodes.values()), edges=edges)



class WisdomEntry(BaseModel):
    id: str
    mind_name: str
    category: str
    title: str
    content: str
    claim_type: str
    tags: str


class GraphNode(BaseModel):
    id: str
    label: str
    type: str   # "angel" | "layer" | "category"
    weight: int


class GraphEdge(BaseModel):
    source: str
    target: str
    strength: float


class GraphData(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


@router.get("/seed/wisdom")
async def get_wisdom(
    angel: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSessionDep = None,
):
    """Return seed wisdom entries — what the engine has learned so far."""
    mind_name = _ANGEL_LENSES.get(angel or "", {}).get("mind_name") if angel else None
    entries = await get_entries(
        db,
        mind_name=mind_name,
        category=category,
        limit=limit,
    )
    return [
        {
            "id": str(e.id),
            "mind_name": e.mind_name,
            "category": e.category,
            "title": e.title,
            "content": e.content[:300],
            "claim_type": e.claim_type,
            "tags": e.tags or "",
        }
        for e in entries
    ]


@router.get("/seed/graph", response_model=GraphData)
async def get_graph(db: AsyncSessionDep):
    """Return graph nodes + edges built from all seeded wisdom."""
    entries = await get_entries(db, mind_name=None, category=None, limit=500)

    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    for e in entries:
        # Angel node
        if e.mind_name not in nodes:
            nodes[e.mind_name] = GraphNode(id=e.mind_name, label=e.mind_name.replace("_mind",""), type="angel", weight=0)
        nodes[e.mind_name].weight += 1

        # Category node
        if e.category not in nodes:
            nodes[e.category] = GraphNode(id=e.category, label=e.category, type="category", weight=0)
        nodes[e.category].weight += 1

        # Edge: angel → category
        edges.append(GraphEdge(source=e.mind_name, target=e.category, strength=1.0))

    return GraphData(nodes=list(nodes.values()), edges=edges)
