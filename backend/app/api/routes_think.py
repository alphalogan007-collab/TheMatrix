"""routes_think.py — User input → engine processes → response.

The user types anything. The engine runs it through Y-Theory against
all seeded wisdom. Response comes back with the layer that answered
and any new patterns formed.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.db.session import AsyncSessionDep
from app.core.angel_manual_service import process_content_into_mind, auto_select_angel

router = APIRouter()


class ThinkRequest(BaseModel):
    text: str
    subject: str = "general"


class ThinkResponse(BaseModel):
    angel: str
    entries_written: int
    y_layer: str
    mind_name: str
    summary: str


@router.post("/think", response_model=ThinkResponse)
async def think(req: ThinkRequest, db: AsyncSessionDep):
    """Process user input through the Y-Theory engine."""
    angel = auto_select_angel(req.subject or req.text[:80])
    result = await process_content_into_mind(
        db,
        angel_name=angel,
        subject=req.subject,
        raw_content=req.text,
    )
    return ThinkResponse(
        angel=result.get("angel", angel),
        entries_written=result.get("entries_written", 0),
        y_layer=result.get("y_layer", ""),
        mind_name=result.get("mind_name", ""),
        summary=result.get("summary", ""),
    )
