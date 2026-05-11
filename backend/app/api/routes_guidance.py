"""routes_guidance.py — Guidance corpus read endpoints + upload.

All Redis-only. No DB. Works in topology-only mode.

GET  /guidance/list         — list all consumed files (metadata)
GET  /guidance/{file_id}    — full content of one file
GET  /guidance/events       — recent consumption events from Redis stream
POST /guidance/upload       — drop a file into guidance inbox for the scanner
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File

from app.config import get_settings
from app.db.redis_client import get_redis

router = APIRouter()


@router.get("/guidance/list")
async def list_guidance(
    limit: int = Query(100, le=500),
    redis=Depends(get_redis),
):
    """List all consumed guidance files (title, source, chars, ts). No content."""
    raw = await redis.hgetall("guidance:corpus")
    items = []
    for file_id, value in raw.items():
        try:
            entry = json.loads(value)
            items.append({
                "file_id": file_id,
                "title":   entry.get("title", ""),
                "source":  entry.get("source", ""),
                "chars":   entry.get("chars", 0),
                "ts":      entry.get("ts", ""),
            })
        except Exception:
            continue
    items.sort(key=lambda x: x["ts"], reverse=True)
    return items[:limit]


@router.get("/guidance/{file_id}")
async def get_guidance(
    file_id: str,
    redis=Depends(get_redis),
):
    """Get full content of a consumed guidance file."""
    raw = await redis.hget("guidance:corpus", file_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Guidance file not found")
    return json.loads(raw)


@router.get("/guidance/events/recent")
async def get_guidance_events(
    count: int = Query(20, le=100),
    redis=Depends(get_redis),
):
    """Recent guidance consumption events from Redis stream."""
    results = await redis.xrevrange("guidance:events", count=count)
    events = []
    for msg_id, fields in results:
        events.append({"msg_id": msg_id, **fields})
    return events


@router.post("/guidance/upload")
async def upload_guidance(
    file: UploadFile = File(...),
    settings=Depends(get_settings),
):
    """Upload a file to the guidance inbox. The scanner picks it up within 5s.

    Supported: .pdf, .txt, .md, .html, .url, .link
    Max size: 200 MB
    """
    ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".html", ".htm", ".url", ".link"}
    MAX_BYTES = 200 * 1024 * 1024  # 200 MB

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    inbox = Path(settings.guidance_inbox)
    inbox.mkdir(parents=True, exist_ok=True)
    dest = inbox / (file.filename or "upload.bin")

    # Stream to disk with size cap
    bytes_written = 0
    with dest.open("wb") as out:
        while chunk := await file.read(1024 * 1024):  # 1 MB chunks
            bytes_written += len(chunk)
            if bytes_written > MAX_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File too large (max 200 MB)")
            out.write(chunk)

    return {
        "status": "queued",
        "filename": file.filename,
        "bytes": bytes_written,
        "inbox": str(inbox),
        "message": "File saved to guidance inbox. Scanner will process it within 5 seconds.",
    }
