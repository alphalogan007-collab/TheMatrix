"""routes_quran.py — Load the full Quran into guidance:corpus.

Fetches Arabic text + English (Sahih International) from the free
alquran.cloud API.  Stores each Surah as one guidance:corpus entry so
the knowledge-absorption training loop can process it immediately.

Routes:
  POST /admin/quran/load      — start loading all 114 surahs
  GET  /admin/quran/status    — progress
  POST /admin/quran/stop      — graceful stop
  GET  /quran/revelation-order — list surahs in revelation sequence
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger("quran")

# Revelation order (Ibn Abbas narration)
REVELATION_ORDER: list[int] = [
    96, 68, 73, 74, 1, 111, 81, 87, 92, 89, 93, 94, 103, 100, 108,
    102, 107, 109, 105, 113, 114, 112, 53, 80, 97, 91, 85, 95, 106, 101,
    75, 104, 77, 50, 90, 86, 54, 38, 7, 72, 36, 25, 35, 19, 20, 56,
    26, 27, 28, 17, 10, 11, 12, 15, 6, 37, 31, 34, 39, 40, 41, 42,
    43, 44, 45, 46, 51, 88, 18, 16, 71, 14, 21, 23, 32, 52, 67, 69,
    70, 78, 79, 82, 84, 30, 29, 83, 2, 8, 3, 33, 60, 4, 99, 57,
    47, 13, 55, 76, 65, 98, 59, 24, 22, 63, 58, 49, 66, 64, 61, 62,
    48, 5, 9, 110,
]

QURAN_API = "https://api.alquran.cloud/v1"
_load_job: dict[str, Any] = {"status": "idle"}


async def _fetch_surah(client: httpx.AsyncClient, num: int) -> dict:
    # Fetch Arabic and English (Sahih International) in parallel
    r_ar, r_en = await asyncio.gather(
        client.get(f"{QURAN_API}/surah/{num}", timeout=30),
        client.get(f"{QURAN_API}/surah/{num}/en.sahih", timeout=30),
    )
    r_ar.raise_for_status()
    r_en.raise_for_status()
    data_ar = r_ar.json()["data"]
    data_en = r_en.json()["data"]

    # Interleave: Arabic verse then English translation on the next line
    verses = []
    en_ayahs = {v["numberInSurah"]: v["text"] for v in data_en["ayahs"]}
    for v in data_ar["ayahs"]:
        n = v["numberInSurah"]
        verses.append(f"{n}. {v['text']}")
        if n in en_ayahs:
            verses.append(f"   [{en_ayahs[n]}]")

    return {
        "number": num,
        "name_ar": data_ar["name"],
        "name_en": data_ar["englishName"],
        "name_en_meaning": data_ar.get("englishNameTranslation", ""),
        "revelation": data_ar.get("revelationType", ""),
        "verse_count": data_ar["numberOfAyahs"],
        "verses_bilingual": "\n".join(verses),
    }


def _to_corpus_entry(surah: dict, rev_pos: int) -> dict:
    meaning = f" ({surah['name_en_meaning']})" if surah.get("name_en_meaning") else ""
    content = (
        f"{surah['name_ar']} — {surah['name_en']}{meaning}\n"
        f"Type: {surah['revelation']} | Verses: {surah['verse_count']} | Revelation position: {rev_pos}/114\n\n"
        f"{surah['verses_bilingual']}"
    )
    return {
        "title": f"القرآن {surah['number']}: {surah['name_ar']} — {surah['name_en']} [rev {rev_pos}/114]",
        "content": content,
        "source": f"alquran.cloud | surah {surah['number']} | {surah['revelation']} | bilingual",
        "ts": datetime.now(timezone.utc).isoformat(),
        "chars": len(content),
    }


async def _run_load(redis_url: str, start_from: int) -> None:
    import redis.asyncio as aioredis
    r = aioredis.from_url(redis_url, decode_responses=True)
    try:
        _load_job.update({
            "status": "running", "total": 114, "done": start_from,
            "loaded": 0, "errors": 0, "current": None, "last_error": None,
            "started_at": datetime.now(timezone.utc).isoformat(),
        })
        async with httpx.AsyncClient() as client:
            for i, surah_num in enumerate(REVELATION_ORDER[start_from:]):
                if _load_job.get("stop"):
                    _load_job["status"] = "stopped"
                    return
                rev_pos = start_from + i + 1
                _load_job["current"] = f"Surah {surah_num} ({rev_pos}/114)"
                try:
                    surah = await _fetch_surah(client, surah_num)
                    entry = _to_corpus_entry(surah, rev_pos)
                    await r.hset("guidance:corpus", f"quran_surah_{surah_num:03d}", json.dumps(entry))
                    await r.sadd("guidance:index", f"quran_surah_{surah_num:03d}")
                    _load_job["done"] = start_from + i + 1
                    _load_job["loaded"] = _load_job.get("loaded", 0) + 1
                    logger.info("[%d/114] Surah %d %s — %d chars", rev_pos, surah_num, surah["name_ar"], entry["chars"])
                except Exception as exc:
                    _load_job["errors"] = _load_job.get("errors", 0) + 1
                    _load_job["last_error"] = f"Surah {surah_num}: {exc}"
                    logger.error("Surah %d failed: %s", surah_num, exc)
                await asyncio.sleep(0.5)
        _load_job["status"] = "complete"
        _load_job["finished_at"] = datetime.now(timezone.utc).isoformat()
        logger.info("Quran load complete — %d surahs", _load_job["loaded"])
    except Exception as exc:
        _load_job["status"] = "error"
        _load_job["last_error"] = str(exc)
    finally:
        await r.aclose()


class QuranLoadBody(BaseModel):
    start_from: int = 0


@router.post("/admin/quran/load")
async def admin_quran_load(body: QuranLoadBody):
    if _load_job.get("status") == "running":
        return {"ok": False, "msg": "Already running", "job": _load_job}
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    _load_job["stop"] = False
    asyncio.create_task(_run_load(redis_url, body.start_from))
    return {"ok": True, "msg": "Quran load started", "total": 114, "start_from": body.start_from}


@router.get("/admin/quran/status")
async def admin_quran_status():
    return _load_job


@router.post("/admin/quran/stop")
async def admin_quran_stop():
    _load_job["stop"] = True
    return {"ok": True, "msg": "Stop requested"}


@router.get("/quran/revelation-order")
async def revelation_order():
    return [{"position": i + 1, "surah_number": n} for i, n in enumerate(REVELATION_ORDER)]