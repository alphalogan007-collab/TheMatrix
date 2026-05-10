"""learn/text.py — Feed raw text into the Y-Theory engine.

Flow:
  raw text → chunk by paragraph → engine processes each chunk
  → wisdom extracted at each Y-Theory layer → seed_mind updated automatically

Usage:
  await ingest_text(db, source="quran", subject="Creation order", text=raw)
"""

from __future__ import annotations

import textwrap
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession


CHUNK_SIZE = 800  # characters per chunk — fits LLM context comfortably


def _chunk(text: str, size: int = CHUNK_SIZE) -> list[str]:
    """Split text into paragraph-aware chunks."""
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks, current = [], ""
    for p in paragraphs:
        if len(current) + len(p) > size and current:
            chunks.append(current.strip())
            current = p
        else:
            current = f"{current}\n{p}" if current else p
    if current:
        chunks.append(current.strip())
    return chunks


async def ingest_text(
    db: AsyncSession,
    *,
    source: str,          # e.g. "quran", "y_theory", "cosmology", "biology"
    subject: str,         # e.g. "Angels and their roles"
    text: str,
    angel_name: Optional[str] = None,  # if None — auto-selected by engine
) -> dict:
    """Ingest raw text. Each chunk is processed independently by the engine."""
    from app.core.angel_manual_service import process_content_into_mind, auto_select_angel

    angel = angel_name or auto_select_angel(subject)
    chunks = _chunk(text)
    total_entries = 0

    for i, chunk in enumerate(chunks):
        result = await process_content_into_mind(
            db,
            angel_name=angel,
            subject=f"{source}: {subject} (part {i + 1}/{len(chunks)})",
            raw_content=chunk,
        )
        total_entries += result.get("entries_written", 0)

    return {
        "source": source,
        "subject": subject,
        "angel": angel,
        "chunks": len(chunks),
        "total_entries": total_entries,
    }
