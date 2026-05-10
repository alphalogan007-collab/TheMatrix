"""
Social Fork router — Content Creator AI Suite.
All /social-fork/* endpoints extracted from main.py for independent deployment.
"""

from __future__ import annotations

import json as _json
import os
import re as _re
import uuid as _uuid
from datetime import datetime as _dt, timezone as _tz

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.db.session import AsyncSessionDep

router = APIRouter(tags=["social_fork"])


# ── Social Fork: Content Expand ────────────────────────────────────────────

@router.post("/social-fork/content/expand", include_in_schema=False)
async def expand_content(request: Request, db: AsyncSessionDep):
    body = await request.json()
    idea  = (body.get("idea") or "").strip()[:500]
    niche = (body.get("niche") or "content creation").strip()[:80]
    if not idea:
        return JSONResponse({"error": "idea is required"}, status_code=400)
    return JSONResponse({
        "status": "training",
        "message": (
            "Content expansion requires a trained knowledge base. "
            "Feed the mind first: POST /manual/start with your topic. "
            "The topology (body\u2192mind) will process it and build understanding."
        ),
        "idea": idea,
        "niche": niche,
        "provider": "none",
    })


# ── Social Fork: Image Generation ─────────────────────────────────────────

@router.post("/social-fork/content/image", include_in_schema=False)
async def generate_image_content(request: Request, db: AsyncSessionDep):
    from app.core.seed_mind_store import write_entry
    from app.core.seed_mind_memory import WISDOM_EXTRACTED

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    idea     = (body.get("idea") or "").strip()
    style    = (body.get("style") or "photorealistic, high-quality, professional").strip()
    niche    = (body.get("niche") or "content creation").strip()
    platform = (body.get("platform") or "instagram").strip().lower()

    if not idea:
        return JSONResponse({"error": "idea is required"}, status_code=422)

    size_guide = {
        "instagram": "square 1:1 ratio",
        "instagram_story": "vertical 9:16 ratio, portrait",
        "youtube": "wide 16:9 landscape thumbnail",
        "tiktok": "vertical 9:16 ratio",
        "linkedin": "wide 1.91:1 landscape",
        "twitter": "wide 16:9 or square",
    }.get(platform, "square 1:1 ratio")

    # Build prompt from raw idea — no LLM, direct composition
    crafted_prompt = f"{idea}, {style}, {size_guide}, professional photography"
    alt_text       = f"AI-generated image: {idea[:80]}"
    caption_hint   = idea[:100]

    image_url = None
    dalle_error = None
    openai_key = os.environ.get("OPENAI_API_KEY", "")

    if openai_key:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                dalle_size = "1024x1024"
                if "9:16" in size_guide or "portrait" in size_guide:
                    dalle_size = "1024x1792"
                elif "16:9" in size_guide or "landscape" in size_guide:
                    dalle_size = "1792x1024"

                resp = await client.post(
                    "https://api.openai.com/v1/images/generations",
                    headers={"Authorization": f"Bearer {openai_key}",
                             "Content-Type": "application/json"},
                    json={"model": "dall-e-3", "prompt": crafted_prompt,
                          "n": 1, "size": dalle_size, "quality": "standard"}
                )
                if resp.status_code == 200:
                    image_url = resp.json()["data"][0]["url"]
                else:
                    dalle_error = f"DALL-E {resp.status_code}: {resp.text[:80]}"
        except Exception as e:
            dalle_error = str(e)[:80]

    try:
        await write_entry(db, mind_name="social_fork_mind",
            category=WISDOM_EXTRACTED,
            title=f"image_gen:{platform}:{idea[:40]}",
            content=f"Platform: {platform}\nIdea: {idea}\nPrompt: {crafted_prompt}\nGenerated: {'yes' if image_url else 'prompt_only'}",
            claim_type="ESTABLISHED_FACT",
            tags="social_fork,image_generation,creator_output")
        await db.commit()
    except Exception:
        pass

    return JSONResponse({
        "prompt": crafted_prompt,
        "alt_text": alt_text,
        "caption_hint": caption_hint,
        "platform": platform,
        "style": style,
        "image_url": image_url,
        "dalle_available": bool(openai_key),
        "dalle_error": dalle_error,
        "llm_provider": "none",
        "original_idea": idea,
        "usage": (
            "image_url is set if OPENAI_API_KEY env var is configured. "
            "Otherwise use the 'prompt' field with any image AI (Midjourney, Stable Diffusion, Canva AI, etc.)"
        ),
    })


# ── Social Fork: Video Script ──────────────────────────────────────────────

@router.post("/social-fork/content/video-script", include_in_schema=False)
async def generate_video_script(request: Request, db: AsyncSessionDep):
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    idea     = (body.get("idea") or "").strip()
    platform = (body.get("platform") or "tiktok").strip().lower()
    duration = max(15, min(600, int(body.get("duration") or 60)))
    if not idea:
        return JSONResponse({"error": "idea is required"}, status_code=422)
    return JSONResponse({
        "status": "training",
        "message": (
            "Video script generation requires a trained knowledge base. "
            "Feed the mind first: POST /manual/start with your topic."
        ),
        "idea": idea, "platform": platform, "duration_s": duration,
        "provider": "none",
    })


# ── Social Fork: Realistic Video ───────────────────────────────────────────

@router.post("/social-fork/content/realistic-video", include_in_schema=False)
async def generate_realistic_video(request: Request, db: AsyncSessionDep):
    from app.core.seed_mind_store import write_entry
    from app.core.seed_mind_memory import WISDOM_EXTRACTED

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    idea     = (body.get("idea") or "").strip()
    script   = (body.get("script") or "").strip()
    avatar   = (body.get("avatar") or "").strip()
    provider = (body.get("provider") or "auto").strip().lower()
    style    = (body.get("style") or "cinematic").strip().lower()
    duration = max(5, min(60, int(body.get("duration") or 5)))

    if not idea:
        return JSONResponse({"error": "idea is required"}, status_code=422)

    runway_key = os.environ.get("RUNWAY_API_KEY", "")
    heygen_key = os.environ.get("HEYGEN_API_KEY", "")

    if provider == "auto":
        if heygen_key and script:
            provider = "heygen"
        elif runway_key:
            provider = "runway"
        else:
            provider = "none"

    # Build prompt directly — no LLM
    gen_prompt = f"{idea}, {style} style, professional video, high quality, smooth camera movement"

    video_url = None
    job_id = None
    status = "prompt_only"
    estimated_seconds = None
    error = None

    if provider == "runway" and runway_key:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://api.dev.runwayml.com/v1/image_to_video",
                    headers={"Authorization": f"Bearer {runway_key}",
                             "Content-Type": "application/json",
                             "X-Runway-Version": "2024-11-06"},
                    json={"model": "gen3a_turbo", "promptText": gen_prompt,
                          "duration": duration, "ratio": "16:9", "watermark": False}
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    job_id = data.get("id")
                    status = data.get("status", "submitted")
                    estimated_seconds = duration * 8
                else:
                    error = f"Runway {resp.status_code}: {resp.text[:100]}"
                    status = "api_error"
        except Exception as e:
            error = str(e)[:100]
            status = "error"

    elif provider == "heygen" and heygen_key:
        try:
            import httpx
            use_script = script or idea
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://api.heygen.com/v2/video/generate",
                    headers={"X-Api-Key": heygen_key, "Content-Type": "application/json"},
                    json={
                        "video_inputs": [{
                            "character": {"type": "avatar", "avatar_id": avatar or "default", "avatar_style": "normal"},
                            "voice": {"type": "text", "input_text": use_script[:1500]},
                            "background": {"type": "color", "value": "#f6f6fc"}
                        }],
                        "aspect_ratio": "9:16",
                        "test": False,
                    }
                )
                if resp.status_code in (200, 201):
                    job_id = resp.json().get("data", {}).get("video_id")
                    status = "processing"
                    estimated_seconds = 60
                else:
                    error = f"HeyGen {resp.status_code}: {resp.text[:100]}"
                    status = "api_error"
        except Exception as e:
            error = str(e)[:100]
            status = "error"

    try:
        await write_entry(db, mind_name="social_fork_mind",
            category=WISDOM_EXTRACTED,
            title=f"realistic_video:{provider}:{idea[:40]}",
            content=f"Provider: {provider}\nStyle: {style}\nDuration: {duration}s\nStatus: {status}\nPrompt: {gen_prompt[:200]}",
            claim_type="ESTABLISHED_FACT",
            tags="social_fork,video_generation,realistic_video,creator_output")
        await db.commit()
    except Exception:
        pass

    return JSONResponse({
        "generation_prompt": gen_prompt,
        "provider": provider,
        "status": status,
        "job_id": job_id,
        "video_url": video_url,
        "estimated_seconds": estimated_seconds,
        "duration_s": duration,
        "style": style,
        "error": error,
        "runway_available": bool(runway_key),
        "heygen_available": bool(heygen_key),
        "manual_instructions": (
            "No API key set — use the 'generation_prompt' with:\n"
            "• Runway ML: app.runwayml.com → Gen-3 Alpha → text-to-video\n"
            "• HeyGen: app.heygen.com → AI Video → paste script\n"
            "• Pika Labs: pika.art → paste prompt\n"
            "• Kling AI: klingai.com → text-to-video"
        ) if provider == "none" else None,
        "original_idea": idea,
    })


# ── Social Fork: Schedule ──────────────────────────────────────────────────

@router.post("/social-fork/schedule", include_in_schema=False)
async def schedule_content(request: Request, db: AsyncSessionDep):
    from app.core.seed_mind_store import write_entry
    from app.core.seed_mind_memory import WISDOM_EXTRACTED

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    content_body  = body.get("content") or {}
    platforms     = body.get("platforms") or ["twitter", "instagram"]
    schedule_at   = (body.get("schedule_at") or "now").strip()
    handle        = (body.get("creator_handle") or "").strip()

    text      = (content_body.get("text") or "").strip()
    image_url = (content_body.get("image_url") or "").strip()
    video_url = (content_body.get("video_url") or "").strip()

    if not text and not image_url and not video_url:
        return JSONResponse({"error": "content must have at least text, image_url, or video_url"}, status_code=422)

    queue_id = f"sfq_{_uuid.uuid4().hex[:16]}"
    now_utc  = _dt.now(_tz.utc)
    scheduled_at = now_utc.isoformat() if schedule_at == "now" else schedule_at

    platform_results = {}
    posting_instructions = {}

    platform_keys = {
        "twitter":   os.environ.get("TWITTER_BEARER_TOKEN", ""),
        "instagram": os.environ.get("INSTAGRAM_ACCESS_TOKEN", ""),
        "linkedin":  os.environ.get("LINKEDIN_ACCESS_TOKEN", ""),
        "tiktok":    os.environ.get("TIKTOK_ACCESS_TOKEN", ""),
        "youtube":   os.environ.get("YOUTUBE_OAUTH_TOKEN", ""),
    }

    for platform in platforms:
        key = platform_keys.get(platform, "")
        if not key:
            posting_instructions[platform] = {
                "status": "manual_required",
                "instruction": {
                    "twitter":   "Post via Twitter/X app or api.twitter.com/2/tweets (Bearer token required)",
                    "instagram": "Post via Instagram Graph API (access token + business account required)",
                    "linkedin":  "Post via LinkedIn API (OAuth2 access token required)",
                    "tiktok":    "Post via TikTok Content Posting API (OAuth2 required)",
                    "youtube":   "Upload via YouTube Data API v3 (OAuth2 required)",
                }.get(platform, "Platform API key not configured"),
                "content_ready": text[:280] if platform == "twitter" else text,
            }
            platform_results[platform] = "manual_required"
        else:
            if platform == "twitter":
                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=15) as client:
                        resp = await client.post(
                            "https://api.twitter.com/2/tweets",
                            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                            json={"text": text[:280]}
                        )
                        if resp.status_code in (200, 201):
                            tweet_id = resp.json().get("data", {}).get("id")
                            platform_results[platform] = {"status": "posted", "id": tweet_id}
                        else:
                            platform_results[platform] = {"status": "error", "code": resp.status_code}
                except Exception as e:
                    platform_results[platform] = {"status": "error", "detail": str(e)[:60]}
            else:
                platform_results[platform] = "queued"

    try:
        await write_entry(db, mind_name="social_fork_mind",
            category=WISDOM_EXTRACTED,
            title=f"scheduled_post:{queue_id}",
            content=(
                f"Queue ID: {queue_id}\nHandle: {handle}\nPlatforms: {', '.join(platforms)}\n"
                f"Scheduled: {scheduled_at}\nText: {text[:200]}\n"
                f"Has image: {'yes' if image_url else 'no'}\nHas video: {'yes' if video_url else 'no'}"
            ),
            claim_type="ESTABLISHED_FACT",
            tags=f"social_fork,scheduled_post,{','.join(platforms)}")
        await db.commit()
    except Exception:
        pass

    return JSONResponse({
        "queue_id": queue_id,
        "scheduled_at": scheduled_at,
        "platforms": platforms,
        "status": "scheduled",
        "platform_results": platform_results,
        "posting_instructions": posting_instructions if posting_instructions else None,
        "content_preview": {
            "text_chars": len(text),
            "text_preview": text[:100] + "..." if len(text) > 100 else text,
            "has_image": bool(image_url),
            "has_video": bool(video_url),
        },
        "note": (
            "To enable automatic posting, set environment variables: "
            "TWITTER_BEARER_TOKEN, INSTAGRAM_ACCESS_TOKEN, "
            "LINKEDIN_ACCESS_TOKEN, TIKTOK_ACCESS_TOKEN, YOUTUBE_OAUTH_TOKEN"
        ),
    })


# ── Social Fork: Schedule Queue ────────────────────────────────────────────

@router.get("/social-fork/schedule/queue", include_in_schema=False)
async def get_schedule_queue(db: AsyncSessionDep, limit: int = 20):
    from app.core.seed_mind_store import get_own_entries
    from app.core.seed_mind_memory import WISDOM_EXTRACTED

    entries = await get_own_entries(
        db, mind_name="social_fork_mind", category=WISDOM_EXTRACTED, limit=limit)
    posts = [e for e in entries if e.title.startswith("scheduled_post:")]

    return {
        "total": len(posts),
        "queue": [
            {"queue_id": e.title.replace("scheduled_post:", ""),
             "content": (e.content or "")[:300],
             "tags": e.tags,
             "at": str(e.created_at)[:16] if e.created_at else ""}
            for e in posts
        ]
    }


# ── Social Fork: Trends ────────────────────────────────────────────────────

@router.get("/social-fork/trends", include_in_schema=False)
async def social_fork_trends(db: AsyncSessionDep, limit: int = 10):
    from app.core.seed_mind_store import get_own_entries
    from app.core.seed_mind_memory import WISDOM_EXTRACTED
    from sqlalchemy import select
    from app.models.seed_mind_memory import SeedMindMemoryEntry

    results = await db.execute(
        select(SeedMindMemoryEntry)
        .where(SeedMindMemoryEntry.is_current == True)
        .where(SeedMindMemoryEntry.category == WISDOM_EXTRACTED)
        .where(SeedMindMemoryEntry.tags.contains("wanderer"))
        .order_by(SeedMindMemoryEntry.created_at.desc())
        .limit(limit)
    )
    entries = results.scalars().all()
    return {
        "trends": [
            {"title": e.title, "content": (e.content or "")[:300],
             "tags": e.tags, "mind": e.mind_name,
             "at": str(e.created_at)[:16] if e.created_at else ""}
            for e in entries
        ],
        "total": len(entries),
    }


# ── Social Fork: Dashboard ─────────────────────────────────────────────────

@router.get("/social-fork/dashboard", include_in_schema=False)
async def social_fork_dashboard_page(db: AsyncSessionDep):
    from app.core.seed_mind_store import get_own_entries
    from app.core.seed_mind_memory import (
        MISSION_PURPOSE, TECHNICAL_ARCHITECTURE, SELF_REFLECTION,
        QUESTION_TO_EXPLORE, WISDOM_EXTRACTED,
    )

    mission   = await get_own_entries(db, mind_name="social_fork_mind", category=MISSION_PURPOSE, limit=1)
    arch      = await get_own_entries(db, mind_name="social_fork_mind", category=TECHNICAL_ARCHITECTURE, limit=10)
    reflect   = await get_own_entries(db, mind_name="social_fork_mind", category=SELF_REFLECTION, limit=5)
    questions = await get_own_entries(db, mind_name="social_fork_mind", category=QUESTION_TO_EXPLORE, limit=5)
    wisdom    = await get_own_entries(db, mind_name="social_fork_mind", category=WISDOM_EXTRACTED, limit=5)

    mission_text = (mission[0].content if mission else "Social Fork not yet seeded.")[:300]
    arch_rows = "".join(f"<li><b>{e.title.split(':')[1] if ':' in e.title else e.title}</b> — {(e.content or '')[:120]}...</li>" for e in arch)
    reflect_rows = "".join(f"<div class='entry'>{(e.content or '')[:200]}...</div>" for e in reflect)
    q_rows = "".join(f"<li>{(e.content or '')[:120]}</li>" for e in questions)
    wisdom_rows = "".join(f"<div class='entry'><b>{e.title[:60]}</b><br>{(e.content or '')[:150]}...</div>" for e in wisdom)

    html = f"""<!DOCTYPE html><html><head>
<title>Social Fork Mind</title><meta charset="utf-8">
<style>
body{{background:#0a0a14;color:#d0d0d0;font-family:monospace;padding:24px;margin:0}}
h1{{color:#ff6b9d;font-size:1.4em}}
h2{{color:#90c8ff;font-size:1em;margin:20px 0 8px;border-bottom:1px solid #222;padding-bottom:4px}}
.mission{{background:#111;border-left:3px solid #ff6b9d;padding:12px;border-radius:4px;margin-bottom:16px}}
ul{{padding-left:20px;line-height:1.8}}
li{{margin-bottom:6px;font-size:0.9em}}
.entry{{background:#0d0d18;padding:8px 12px;border-radius:4px;margin-bottom:8px;font-size:0.85em;border:1px solid #1a1a2e}}
.badge{{display:inline-block;background:#ff6b9d22;border:1px solid #ff6b9d66;
        color:#ff6b9d;padding:3px 12px;border-radius:20px;font-size:0.8em;margin-bottom:16px}}
.expand-form{{background:#111;border:1px solid #333;padding:16px;border-radius:8px;margin:16px 0}}
input,textarea{{background:#0a0a14;border:1px solid #333;color:#d0d0d0;padding:6px;
                border-radius:4px;font-family:monospace;width:100%;margin-bottom:8px;box-sizing:border-box}}
.btn{{background:#ff6b9d22;color:#ff6b9d;border:1px solid #ff6b9d66;padding:8px 20px;
      border-radius:6px;cursor:pointer;font-family:monospace}}
select{{background:#0a0a14;border:1px solid #333;color:#d0d0d0;padding:6px;
        border-radius:4px;font-family:monospace;margin-bottom:8px}}
.tool-row{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}}
.tool-card{{background:#111;border:1px solid #2a2a3e;border-radius:8px;padding:12px;flex:1;min-width:200px}}
.tool-card h3{{color:#ff6b9d;font-size:0.85em;margin:0 0 8px}}
</style></head><body>
<h1>Social Fork Mind</h1>
<span class="badge">PRODUCT 2 — CONTENT CREATOR ECOSYSTEM</span>

<div class="mission">{mission_text}</div>

<div class="tool-row">
  <div class="tool-card">
    <h3>TEXT → 5 FORMATS</h3>
    <textarea id="idea" placeholder="Raw idea..." rows="2"></textarea>
    <input id="niche" placeholder="Niche (Islamic finance, fitness...)">
    <button class="btn" onclick="expand()">EXPAND →</button>
    <div id="expand_result" style="margin-top:8px;white-space:pre-wrap;font-size:0.78em;color:#a0c8ff"></div>
  </div>
  <div class="tool-card">
    <h3>IMAGE PROMPT</h3>
    <textarea id="img_idea" placeholder="Image idea..." rows="2"></textarea>
    <select id="img_platform"><option value="instagram">Instagram</option><option value="tiktok">TikTok</option><option value="youtube">YouTube</option><option value="linkedin">LinkedIn</option></select>
    <button class="btn" onclick="genImage()">IMAGE →</button>
    <div id="img_result" style="margin-top:8px;white-space:pre-wrap;font-size:0.78em;color:#a0c8ff"></div>
  </div>
  <div class="tool-card">
    <h3>VIDEO SCRIPT</h3>
    <textarea id="vid_idea" placeholder="Video idea..." rows="2"></textarea>
    <select id="vid_platform"><option value="tiktok">TikTok</option><option value="reels">Reels</option><option value="youtube_short">YouTube Short</option></select>
    <select id="vid_duration"><option value="30">30s</option><option value="60">60s</option><option value="90">90s</option></select>
    <button class="btn" onclick="genScript()">SCRIPT →</button>
    <div id="script_result" style="margin-top:8px;white-space:pre-wrap;font-size:0.78em;color:#a0c8ff"></div>
  </div>
  <div class="tool-card">
    <h3>REALISTIC VIDEO</h3>
    <textarea id="rv_idea" placeholder="Video scene idea..." rows="2"></textarea>
    <select id="rv_style"><option value="cinematic">Cinematic</option><option value="vlog">Vlog</option><option value="educational">Educational</option><option value="news">News</option></select>
    <button class="btn" onclick="genVideo()">VIDEO PROMPT →</button>
    <div id="rv_result" style="margin-top:8px;white-space:pre-wrap;font-size:0.78em;color:#a0c8ff"></div>
  </div>
</div>

<h2>Architecture ({len(arch)} components)</h2>
<ul>{arch_rows or "<li>Not yet seeded</li>"}</ul>

<h2>Exploration Questions ({len(questions)})</h2>
<ul>{q_rows or "<li>None yet</li>"}</ul>

<h2>Self Reflections ({len(reflect)})</h2>
{reflect_rows or "<div class='entry'>No reflections yet</div>"}

<h2>Wisdom ({len(wisdom)} entries)</h2>
{wisdom_rows or "<div class='entry'>Wanderer has not visited Social Fork topics yet</div>"}

<script>
async function post(url, data) {{
  const r = await fetch(url, {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify(data)}});
  return r.json();
}}
async function expand() {{
  const res = document.getElementById('expand_result');
  res.textContent = 'Expanding...';
  const d = await post('/social-fork/content/expand', {{
    idea: document.getElementById('idea').value,
    niche: document.getElementById('niche').value || 'content creation'
  }});
  if(d.error) {{ res.textContent = 'Error: '+d.error; return; }}
  res.textContent = '🐦 TWEET:\n'+d.tweet+'\n\n📸 INSTAGRAM:\n'+d.instagram+'\n\n▶ YOUTUBE:\n'+d.youtube_desc+'\n\n💼 LINKEDIN:\n'+d.linkedin+'\n\n📝 BLOG:\n'+d.blog_intro+'\n\n🏷 '+d.tags?.join(' ');
}}
async function genImage() {{
  const res = document.getElementById('img_result');
  res.textContent = 'Generating prompt...';
  const d = await post('/social-fork/content/image', {{
    idea: document.getElementById('img_idea').value,
    platform: document.getElementById('img_platform').value
  }});
  if(d.error) {{ res.textContent = 'Error: '+d.error; return; }}
  res.textContent = '🎨 PROMPT:\n'+d.prompt+'\n\nALT: '+d.alt_text+'\nCAPTION: '+d.caption_hint+(d.image_url?'\n\n🖼 '+d.image_url:'\n\n(Set OPENAI_API_KEY for auto-generation)');
}}
async function genScript() {{
  const res = document.getElementById('script_result');
  res.textContent = 'Generating script...';
  const d = await post('/social-fork/content/video-script', {{
    idea: document.getElementById('vid_idea').value,
    platform: document.getElementById('vid_platform').value,
    duration: parseInt(document.getElementById('vid_duration').value)
  }});
  if(d.error) {{ res.textContent = 'Error: '+d.error; return; }}
  res.textContent = '🎬 HOOK:\n'+d.hook+'\n\n'+d.full_script+'\n\n🏷 '+d.hashtags?.join(' ');
}}
async function genVideo() {{
  const res = document.getElementById('rv_result');
  res.textContent = 'Generating video prompt...';
  const d = await post('/social-fork/content/realistic-video', {{
    idea: document.getElementById('rv_idea').value,
    style: document.getElementById('rv_style').value
  }});
  if(d.error) {{ res.textContent = 'Error: '+d.error; return; }}
  res.textContent = '🎥 GENERATION PROMPT:\n'+d.generation_prompt+'\n\n'+(d.video_url?'VIDEO: '+d.video_url:d.manual_instructions||'(Set RUNWAY_API_KEY or HEYGEN_API_KEY for auto-generation)');
}}
</script>
</body></html>"""
    return HTMLResponse(html)
