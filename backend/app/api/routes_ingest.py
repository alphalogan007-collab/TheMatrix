"""routes_ingest.py — Feed any text into the Y-Theory engine.

POST /ingest
  body: { source, subject, text, angel_name? }
  → chunks text → engine processes each chunk
  → wisdom written to seed automatically
  → events emitted on y_event_bus for live graph
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, status
from pydantic import BaseModel

from app.db.session import AsyncSessionDep
from app.core.angel_manual_service import process_content_into_mind, auto_select_angel

router = APIRouter()

CHUNK_SIZE = 800


def _chunk(text: str) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks, current = [], ""
    for p in paragraphs:
        if len(current) + len(p) > CHUNK_SIZE and current:
            chunks.append(current.strip())
            current = p
        else:
            current = f"{current}\n{p}" if current else p
    if current:
        chunks.append(current.strip())
    return chunks or [text]


class IngestIn(BaseModel):
    source: str              # e.g. "quran", "y_theory", "cosmology"
    subject: str             # e.g. "Angels and their roles"
    text: str
    angel_name: Optional[str] = None  # if None — auto-selected


class IngestOut(BaseModel):
    source: str
    subject: str
    angel: str
    chunks: int
    total_entries: int


@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED, response_model=IngestOut)
async def ingest(body: IngestIn, db: AsyncSessionDep) -> IngestOut:
    """Feed text into the Y-Theory engine. Wisdom writes to seed automatically."""
    angel = body.angel_name or auto_select_angel(body.subject)
    chunks = _chunk(body.text)
    total_entries = 0

    for i, chunk in enumerate(chunks):
        result = await process_content_into_mind(
            db,
            angel_name=angel,
            subject=f"{body.source}: {body.subject} (part {i + 1}/{len(chunks)})",
            raw_content=chunk,
        )
        total_entries += result.get("entries_written", 0)

    return IngestOut(
        source=body.source,
        subject=body.subject,
        angel=angel,
        chunks=len(chunks),
        total_entries=total_entries,
    )
