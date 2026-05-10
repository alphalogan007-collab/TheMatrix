"""learn/video.py — Feed video into the Y-Theory engine.

Flow:
  video file / URL
    → extract audio track  (ffmpeg)
    → transcribe audio     (Whisper via learn/sound.py)
    → extract captions     (if available — YouTube subtitles etc.)
    → merge transcript + captions → text
    → learn/text.ingest_text()
    → engine processes → seed_mind updated automatically

Supports: mp4, mkv, avi, mov, YouTube URLs
"""

from __future__ import annotations

import os
import tempfile
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession


async def extract_audio(video_path: str) -> str:
    """Extract audio track from video to a temp wav file using ffmpeg."""
    import asyncio
    tmp = tempfile.mktemp(suffix=".wav")
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", tmp,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.communicate()
    return tmp


async def fetch_youtube_transcript(url: str) -> str:
    """Download YouTube auto-captions as text (no audio download needed)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
        video_id = url.split("v=")[-1].split("&")[0]
        entries = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join(e["text"] for e in entries)
    except Exception:
        return ""


async def ingest_video(
    db: AsyncSession,
    *,
    source: str,           # e.g. "lecture", "documentary"
    subject: str,
    video_path: str,       # local file path or YouTube URL
    angel_name: Optional[str] = None,
) -> dict:
    """Extract text from video then feed into the engine."""
    from learn.text import ingest_text
    from learn.sound import transcribe

    text = ""

    # YouTube URL — prefer transcript (faster, no download)
    if video_path.startswith("http"):
        text = await fetch_youtube_transcript(video_path)

    # Local file or YouTube fallback — extract audio → transcribe
    if not text:
        audio_path = await extract_audio(video_path)
        text = await transcribe(audio_path)
        try:
            os.remove(audio_path)
        except OSError:
            pass

    result = await ingest_text(
        db,
        source=source,
        subject=subject,
        text=text,
        angel_name=angel_name,
    )
    result["video_path"] = video_path
    result["transcript_chars"] = len(text)
    return result
