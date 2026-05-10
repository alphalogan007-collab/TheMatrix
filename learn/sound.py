"""learn/sound.py — Feed audio into the Y-Theory engine.

Flow:
  audio file / URL → transcribe (Whisper) → text → learn/text.ingest_text()
  → engine processes → seed_mind updated automatically

Supports: mp3, mp4 audio, wav, m4a, ogg
Transcription: OpenAI Whisper (local via whisper package or API)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession


async def transcribe(audio_path: str) -> str:
    """Transcribe audio file to text using Whisper."""
    try:
        import whisper  # type: ignore
        model = whisper.load_model("base")
        result = model.transcribe(audio_path)
        return result["text"]
    except ImportError:
        # Fallback: OpenAI Whisper API
        import httpx
        api_key = os.environ.get("OPENAI_API_KEY", "")
        async with httpx.AsyncClient() as client:
            with open(audio_path, "rb") as f:
                resp = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": (Path(audio_path).name, f, "audio/mpeg")},
                    data={"model": "whisper-1"},
                    timeout=120,
                )
            resp.raise_for_status()
            return resp.json()["text"]


async def ingest_sound(
    db: AsyncSession,
    *,
    source: str,           # e.g. "quran_recitation", "lecture"
    subject: str,
    audio_path: str,       # local file path
    angel_name: Optional[str] = None,
) -> dict:
    """Transcribe audio then feed text into the engine."""
    from learn.text import ingest_text

    transcript = await transcribe(audio_path)
    result = await ingest_text(
        db,
        source=source,
        subject=subject,
        text=transcript,
        angel_name=angel_name,
    )
    result["audio_path"] = audio_path
    result["transcript_chars"] = len(transcript)
    return result
