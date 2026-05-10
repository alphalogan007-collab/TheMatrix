"""routes_angel_manuals.py — Angel guidance: pass content, get mind wisdom.

Pass any raw content about a subject → the angel reads it through the Y-Theory
engine lens, extracts structured wisdom, and writes it directly into the angel's
own mind as memory entries (WISDOM_EXTRACTED, TECHNICAL_ARCHITECTURE, RISK_OR_CONFUSION…).

The angel mind becomes the consolidated source seed — any mind reading from it
inherits the accumulated guidance automatically.

Endpoints
---------
  POST /angels/manuals/generate   — pass content, angel writes wisdom to its mind
  GET  /angels/manuals/angels     — list angels + their Y-Theory layer focus
  GET  /angels/manuals/seed       — read consolidated wisdom from an angel mind
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.dependencies import AsyncSessionDep, CurrentUser
from app.core.angel_manual_service import (
    process_content_into_mind,
    auto_select_angel,
    _ANGEL_LENSES,
)
from app.core.seed_mind_store import get_entries

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class ManualGenerateRequest(BaseModel):
    subject: str = Field(max_length=200, description="Topic, e.g. 'React Native navigation'")
    content: str = Field(max_length=20_000, description="Raw content — paste docs, notes, articles")
    angel_name: Optional[str] = Field(default=None, description="Angel to use. Blank = auto-select by subject.")


class ManualResult(BaseModel):
    angel_name: str
    mind_name: str
    subject: str
    title: str
    summary: str
    y_layer: str           # which Y-Theory engine layer this maps to
    entries_written: int
    entry_titles: List[str]
    tags: List[str]
    llm_provider: str
    processed_at: str


class AngelFocusOut(BaseModel):
    name: str
    mind_name: str
    primary_layer: str     # Y-Theory layer
    focus: str
    tone: str


class SeedEntryOut(BaseModel):
    id: str
    category: str
    title: str
    content: str
    claim_type: str
    tags: str
    created_at: str


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

_VALID_ANGELS = set(_ANGEL_LENSES.keys())


@router.post("/manuals/generate", response_model=ManualResult)
async def generate_angel_manual(
    body: ManualGenerateRequest,
    db: AsyncSessionDep,
    current_user: CurrentUser,
) -> ManualResult:
    """Pass any content → angel extracts Y-Theory-mapped wisdom into its mind as source seed."""
    angel = body.angel_name or auto_select_angel(body.subject)

    if angel not in _VALID_ANGELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown angel '{angel}'. Valid: {sorted(_VALID_ANGELS)}",
        )

    result = await process_content_into_mind(
        db=db,
        angel_name=angel,
        subject=body.subject,
        raw_content=body.content,
    )
    return ManualResult(**result)


@router.get("/manuals/angels", response_model=List[AngelFocusOut])
async def list_angel_focuses(current_user: CurrentUser) -> List[AngelFocusOut]:
    """List all angels, their Y-Theory layer, and their domain focus."""
    return [
        AngelFocusOut(
            name=name,
            mind_name=lens["mind_name"],
            primary_layer=lens["primary_layer"],
            focus=lens["focus"],
            tone=lens["tone"],
        )
        for name, lens in _ANGEL_LENSES.items()
    ]


@router.get("/manuals/seed", response_model=List[SeedEntryOut])
async def read_angel_seed(
    db: AsyncSessionDep,
    current_user: CurrentUser,
    angel_name: str = Query(..., description="Angel name, e.g. 'gabriel'"),
    category: Optional[str] = Query(default=None, description="Filter by memory category"),
    limit: int = Query(default=50, le=200),
) -> List[SeedEntryOut]:
    """Read consolidated wisdom from an angel's mind — the source seed for other minds."""
    if angel_name not in _VALID_ANGELS:
        raise HTTPException(status_code=404, detail=f"Angel '{angel_name}' not found.")

    mind_name = _ANGEL_LENSES[angel_name]["mind_name"]
    entries = await get_entries(db, mind_name=mind_name, category=category, limit=limit)

    return [
        SeedEntryOut(
            id=e.id,
            category=e.category,
            title=e.title,
            content=e.content,
            claim_type=e.claim_type or "",
            tags=e.tags or "",
            created_at=e.created_at.isoformat() if e.created_at else "",
        )
        for e in entries
    ]

