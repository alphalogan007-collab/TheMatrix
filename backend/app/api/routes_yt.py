"""routes_yt.py — YouTube video/audio/subtitle extractor → seed:input.

POST /admin/yt/start          — kick off extraction job
GET  /admin/yt/job/{job_id}   — poll job status + per-video progress
GET  /admin/yt/jobs           — list recent jobs

Uses yt-dlp to extract subtitles (or auto-subs) and metadata then pushes
each video as plain text into seed:input.  Playlist mode iterates every
entry automatically.
"""

from __future__ import annotations

import asyncio
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

router = APIRouter()

# In-memory job store  — fine for a single-process admin tool
_jobs: dict[str, dict[str, Any]] = {}

# Global semaphore: limit concurrent yt-dlp calls to 1 to avoid GIL starvation.
# yt-dlp is CPU-heavy Python (JSON parsing, URL work) and holds the GIL,
# starving the uvicorn event loop and blocking all HTTP responses.
_yt_sem: asyncio.Semaphore | None = None


def _get_yt_sem() -> asyncio.Semaphore:
    global _yt_sem
    if _yt_sem is None:
        _yt_sem = asyncio.Semaphore(1)
    return _yt_sem


# ── helpers ───────────────────────────────────────────────────────────────────

def _vtt_to_text(vtt: str) -> str:
    """Strip WEBVTT/SRT cue formatting → plain text."""
    # Remove WEBVTT header block
    text = re.sub(r"^WEBVTT[^\n]*\n+", "", vtt, flags=re.MULTILINE)
    # Remove timestamp lines:  00:00.000 --> 00:05.000  or  00:00:00.000 --> …
    text = re.sub(r"\d[\d:]+\.?\d*\s*-->\s*\d[\d:]+\.?\d*[^\n]*\n", "", text)
    # Remove SRT sequence numbers (lone integer lines)
    text = re.sub(r"^\d+\s*$", "", text, flags=re.MULTILINE)
    # Remove inline VTT tags  <c>, <00:00:01.000>, <b>, etc.
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse excess blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _ts_to_secs(ts: str) -> float:
    """Convert VTT/SRT timestamp HH:MM:SS.mmm or MM:SS.mmm → float seconds."""
    ts = ts.strip().split(".")[0]  # drop millis
    parts = ts.split(":")
    parts = [int(p) for p in parts]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return float(parts[0])


def _vtt_to_scenes(vtt: str, scene_secs: int = 90) -> list[dict]:
    """Parse VTT into timed scene chunks of ~scene_secs each.

    Returns list of:
      {"start_secs": float, "end_secs": float, "start_ts": str, "text": str}
    Each scene groups subtitle cues that fall within a scene_secs window.
    """
    # Parse each cue: (start_secs, end_secs, text)
    cue_re = re.compile(
        r"(\d[\d:]+\.?\d*)\s*-->\s*(\d[\d:]+\.?\d*)[^\n]*\n((?:(?!-->)[^\n]+\n?)*)",
        re.MULTILINE,
    )
    # Strip inline VTT tags first
    vtt_clean = re.sub(r"<[^>]+>", "", vtt)

    cues: list[tuple[float, float, str]] = []
    for m in cue_re.finditer(vtt_clean):
        start = _ts_to_secs(m.group(1))
        end   = _ts_to_secs(m.group(2))
        text  = m.group(3).strip()
        if text:
            cues.append((start, end, text))

    if not cues:
        return []

    scenes: list[dict] = []
    scene_start = cues[0][0]
    scene_texts: list[str] = []
    seen_lines: set[str] = set()  # deduplicate repeated captions

    def _fmt_ts(secs: float) -> str:
        h = int(secs // 3600)
        m = int((secs % 3600) // 60)
        s = int(secs % 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    for start, end, text in cues:
        # New scene boundary
        if start - scene_start >= scene_secs and scene_texts:
            combined = " ".join(scene_texts)
            if combined.strip():
                scenes.append({
                    "start_secs": scene_start,
                    "end_secs":   start,
                    "start_ts":   _fmt_ts(scene_start),
                    "text":       combined.strip(),
                })
            scene_start = start
            scene_texts = []
            seen_lines = set()

        # Deduplicate overlapping auto-caption lines
        if text not in seen_lines:
            scene_texts.append(text)
            seen_lines.add(text)

    # Flush last scene
    if scene_texts:
        combined = " ".join(scene_texts)
        if combined.strip():
            scenes.append({
                "start_secs": scene_start,
                "end_secs":   cues[-1][1],
                "start_ts":   _fmt_ts(scene_start),
                "text":       combined.strip(),
            })

    return scenes


async def _load_scenes_to_corpus(
    redis_url: str,
    scenes: list[dict],
    video_id: str,
    video_title: str,
    video_url: str,
) -> int:
    """Write each scene as a corpus entry: reality_{video_id}_scene_{N:04d}.

    Returns the number of scenes stored.
    Sequential keys ensure fibonacci_pulse training processes them in order:
    scene 1 wisdom is in corpus before scene 2 is processed.
    """
    import redis.asyncio as aioredis
    from datetime import datetime, timezone

    r = aioredis.from_url(redis_url, decode_responses=True)
    stored = 0
    try:
        for i, scene in enumerate(scenes):
            file_id = f"reality_{video_id}_scene_{i+1:04d}"
            title   = f"{video_title} [{scene['start_ts']}]"
            content = (
                f"[Reality Feed — Scene {i+1}/{len(scenes)}]\n"
                f"Source: {video_title}\n"
                f"Timestamp: {scene['start_ts']}\n\n"
                f"{scene['text']}"
            )
            entry = json.dumps({
                "file_id": file_id,
                "title":   title[:300],
                "content": content[:50_000],
                "source":  f"youtube:{video_url}",
                "chars":   len(content),
                "ts":      datetime.now(timezone.utc).isoformat(),
            })
            await r.hset("guidance:corpus", file_id, entry)
            await r.sadd("guidance:index", file_id)
            stored += 1
    finally:
        await r.aclose()
    return stored


def _info_to_text(info: dict) -> str:
    """Convert yt-dlp info dict → human-readable text for seeding."""
    parts: list[str] = []
    if info.get("title"):
        parts.append(f"Title: {info['title']}")
    if info.get("uploader"):
        parts.append(f"Uploader: {info['uploader']}")
    if info.get("upload_date"):
        d = str(info["upload_date"])
        parts.append(f"Upload date: {d[:4]}-{d[4:6]}-{d[6:]}")
    if info.get("duration"):
        m, s = divmod(int(info["duration"]), 60)
        parts.append(f"Duration: {m}m {s}s")
    if info.get("view_count"):
        parts.append(f"Views: {info['view_count']:,}")
    if info.get("webpage_url"):
        parts.append(f"URL: {info['webpage_url']}")
    if info.get("description"):
        parts.append(f"\nDescription:\n{info['description'][:4000]}")
    if info.get("chapters"):
        chs = [
            f"  [{int(ch['start_time'])}s] {ch['title']}"
            for ch in info["chapters"]
        ]
        parts.append(f"\nChapters:\n" + "\n".join(chs))
    return "\n".join(parts)


async def _push_to_seed(redis_url: str, content: str, source: str) -> tuple[str, str]:
    """Push extracted text into seed:input; return (session_id, msg_id)."""
    import redis.asyncio as aioredis

    r = aioredis.from_url(redis_url, decode_responses=True)
    try:
        session_id = uuid.uuid4().hex
        msg_id = await r.xadd(
            "seed:input",
            {
                "input_type": "text",
                "content": content[:50_000],
                "source": source,
                "session_id": session_id,
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        )
        return session_id, str(msg_id)
    finally:
        await r.aclose()


def _extract_raw_vtt(vid_url: str, tmp_dir: str) -> tuple[dict, str]:
    """Like _extract_one_video but returns raw VTT text (unparsed) for scene splitting."""
    import yt_dlp

    sub_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en"],
        "subtitlesformat": "vtt",
        "outtmpl": str(Path(tmp_dir) / "%(id)s.%(ext)s"),
    }
    with yt_dlp.YoutubeDL(sub_opts) as ydl:
        info = ydl.extract_info(vid_url, download=True)

    raw_vtt = ""
    for f in Path(tmp_dir).iterdir():
        if f.suffix in (".vtt", ".srt") and f.stat().st_size > 0:
            raw_vtt = f.read_text(encoding="utf-8", errors="replace")
            break

    return info, raw_vtt


def _extract_one_video(vid_url: str, tmp_dir: str) -> tuple[dict, str]:
    """
    Synchronous yt-dlp call: download subtitles for one video into tmp_dir.
    Returns (info_dict, subtitle_text).
    Raises on yt-dlp errors.
    """
    import yt_dlp  # noqa: PLC0415

    sub_opts = {
        "quiet": False,        # surface errors so they appear in job logs
        "no_warnings": False,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en"],
        "subtitlesformat": "vtt",
        "outtmpl": str(Path(tmp_dir) / "%(id)s.%(ext)s"),
    }
    with yt_dlp.YoutubeDL(sub_opts) as ydl:
        info = ydl.extract_info(vid_url, download=True)

    # Glob for any subtitle file regardless of language tag (.en.vtt, .en-US.vtt, etc.)
    sub_text = ""
    candidates = sorted(
        [f for f in Path(tmp_dir).rglob("*") if f.suffix in (".vtt", ".srt")],
        key=lambda f: f.stat().st_size,
        reverse=True,
    )
    if candidates:
        raw = candidates[0].read_text(encoding="utf-8", errors="replace")
        sub_text = _vtt_to_text(raw)

    return info, sub_text


def _collect_playlist_entries(url: str, playlist: bool) -> list[dict]:
    """Return list of flat entry dicts (id + title) for the URL."""
    import yt_dlp  # noqa: PLC0415

    if playlist:
        # Channel URL  →  append /videos so yt-dlp enumerates all uploads
        # Handles:  /@Handle  /channel/UC...  /c/name  /user/name
        channel_m = re.search(
            r"youtube\.com/((?:@|channel/|c/|user/)[^/?#&]+)",
            url,
        )
        if channel_m:
            handle = channel_m.group(1).rstrip("/")
            url = f"https://www.youtube.com/{handle}/videos"
        else:
            # playlist?list= or watch?v=...&list= — keep list= only
            list_m = re.search(r"[?&]list=([A-Za-z0-9_-]+)", url)
            if list_m:
                url = f"https://www.youtube.com/playlist?list={list_m.group(1)}"

    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": playlist,   # flat = only id/title, no per-video download
        "noplaylist": not playlist,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if playlist and "entries" in info:
        return [e for e in (info.get("entries") or []) if e]

    # Single video — canonical webpage URL only
    return [{
        "id":          info.get("id"),
        "title":       info.get("title") or info.get("id"),
        "webpage_url": info.get("webpage_url") or info.get("original_url") or url,
    }]


# ── background job ────────────────────────────────────────────────────────────

async def _run_job(job_id: str, url: str, playlist: bool, redis_url: str,
                   scene_mode: bool = False, scene_secs: int = 90):
    """Background coroutine: extract each video and push to seed."""
    job = _jobs[job_id]
    job["status"] = "collecting"

    loop = asyncio.get_event_loop()

    # 1. Collect video list (blocking yt-dlp call → thread)
    try:
        entries = await loop.run_in_executor(
            None, _collect_playlist_entries, url, playlist
        )
    except Exception as exc:
        job["status"] = "error"
        job["error"] = str(exc)
        return

    job["total"] = len(entries)
    job["videos"] = [
        {
            "title": e.get("title") or e.get("id") or "?",
            "url":   (
                e.get("webpage_url")
                or e.get("original_url")
                or e.get("url")
                or f"https://www.youtube.com/watch?v={e.get('id','')}"
            ),
            "status": "pending",
            "session_id": None,
            "chars": 0,
        }
        for e in entries
    ]
    job["status"] = "running"
    job["done"] = 0

    # 2. Process each video
    for i, vid in enumerate(job["videos"]):
        # Respect cancellation — set by POST /admin/yt/job/{id}/cancel
        if job.get("cancelled"):
            job["status"] = "cancelled"
            job["finished_at"] = datetime.now(timezone.utc).isoformat()
            return
        vid["status"] = "extracting"
        vid_url = vid["url"]

        try:
            async with _get_yt_sem():
                with tempfile.TemporaryDirectory() as tmp:
                    info, sub_text = await loop.run_in_executor(
                        None, _extract_one_video, vid_url, tmp
                    )

            meta = _info_to_text(info)
            content = meta
            if sub_text:
                content += f"\n\nSubtitles / Transcript:\n{sub_text}"
            content = content.strip()

            if not content:
                vid["status"] = "no_content"
                continue

            vid["title"] = info.get("title") or vid["title"]
            video_id = info.get("id") or re.sub(r"[^a-zA-Z0-9_-]", "_", vid_url)[-40:]

            if scene_mode and sub_text:
                # Find the raw VTT file to parse timestamps (re-extract)
                with tempfile.TemporaryDirectory() as tmp2:
                    _, raw_vtt = await loop.run_in_executor(
                        None, _extract_raw_vtt, vid_url, tmp2
                    )
                scenes = _vtt_to_scenes(raw_vtt or sub_text, scene_secs=scene_secs)
                if not scenes:
                    vid["status"] = "no_scenes"
                    continue
                stored = await _load_scenes_to_corpus(
                    redis_url, scenes, video_id, vid["title"], vid_url
                )
                vid["status"] = "corpus_loaded"
                vid["scenes"] = stored
                vid["chars"] = sum(len(s["text"]) for s in scenes)
                job["done"] = job.get("done", 0) + 1
            else:
                session_id, msg_id = await _push_to_seed(
                    redis_url, content, source=f"youtube:{vid_url}"
                )
                vid["status"] = "seeded"
                vid["session_id"] = session_id
                vid["chars"] = len(content)
                job["done"] = job.get("done", 0) + 1

        except Exception as exc:
            vid["status"] = f"error"
            vid["error"] = str(exc)

    job["status"] = "complete"
    job["finished_at"] = datetime.now(timezone.utc).isoformat()


# ── models ────────────────────────────────────────────────────────────────────

class YTStartBody(BaseModel):
    url: str
    playlist: bool = False
    scene_mode: bool = False   # True: split into corpus scenes (reality feed)
    scene_secs: int = 90       # seconds per scene chunk (default 90s)


# ── routes ────────────────────────────────────────────────────────────────────

@router.post("/admin/yt/start")
async def yt_start(body: YTStartBody, bg: BackgroundTasks):
    """Kick off a YouTube extraction job.  Returns job_id immediately."""
    if not body.url.strip():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="url is required")

    # Resolve redis URL from env (same env the backend container sees)
    import os
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")

    job_id = uuid.uuid4().hex
    _jobs[job_id] = {
        "job_id": job_id,
        "url": body.url,
        "playlist": body.playlist,
        "scene_mode": body.scene_mode,
        "scene_secs": body.scene_secs,
        "status": "queued",
        "total": 0,
        "done": 0,
        "videos": [],
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
    }

    bg.add_task(_run_job, job_id, body.url, body.playlist, redis_url,
                body.scene_mode, body.scene_secs)
    return {"job_id": job_id, "status": "queued"}


@router.get("/admin/yt/job/{job_id}")
async def yt_job_status(job_id: str):
    """Poll extraction job status."""
    if job_id not in _jobs:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="job not found")
    return _jobs[job_id]


@router.post("/admin/yt/job/{job_id}/cancel")
async def yt_job_cancel(job_id: str):
    """Cancel a running job.  Current video finishes, then the loop stops."""
    from fastapi import HTTPException
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="job not found")
    job = _jobs[job_id]
    if job["status"] not in ("queued", "collecting", "running"):
        return {"job_id": job_id, "status": job["status"], "message": "already finished"}
    job["cancelled"] = True
    return {"job_id": job_id, "status": "cancelling"}


@router.get("/admin/yt/jobs")
async def yt_jobs_list():
    """List all jobs (most recent first, max 50)."""
    jobs = sorted(_jobs.values(), key=lambda j: j["created_at"], reverse=True)[:50]
    return {"jobs": jobs}
