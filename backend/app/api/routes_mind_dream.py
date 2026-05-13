"""routes_mind_dream.py -- The mind projection pipe.

The architect and UX team put the product template into guidance knowledge.
The mind reads that knowledge and decides what to project.
This file is ONLY the pipe: command in -> knowledge from Redis -> mind generates -> stream out.
No templates here. No hardcoded content types.

Routes:
  GET  /mind/dream               - minimal delivery screen
  GET  /mind/dream/stream        - SSE: streams what the mind generates
  POST /mind/dream/react         - records user touch behaviour
  GET  /mind/dream/profile/{id}  - what the mind knows about this device
"""

from __future__ import annotations

import json
import logging
import os
import random
from typing import Literal

import redis.asyncio as aioredis
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

log = logging.getLogger("mind_dream")
router = APIRouter()

REDIS_URL   = os.environ.get("REDIS_URL", "redis://redis:6379/0")
PROFILE_TTL = 60 * 60 * 24 * 30


async def _redis() -> aioredis.Redis:
    return await aioredis.from_url(REDIS_URL, decode_responses=True)


async def _pull_guidance(r: aioredis.Redis) -> str:
    """Read dream guidance (all) + product templates (released only).

    Product templates follow the release pipeline:
      requirement -> brainstorm -> design -> architect -> generate -> test -> approval -> released
    The mind only reads templates with status=released.
    All minds share the same knowledge node — a release is instantly visible to all.
    """
    lines = []
    all_keys = await r.hkeys("mind:knowledge")
    for k in all_keys:
        is_dream   = k.startswith("guidance:dream:")
        is_product = k.startswith("guidance:product:")
        if not (is_dream or is_product):
            continue
        raw = await r.hget("mind:knowledge", k)
        if not raw:
            continue
        try:
            e = json.loads(raw)
            # Product templates: only use released versions
            if is_product and e.get("status", "released") != "released":
                continue
            text = (e.get("text") or e.get("content") or "").strip()
            title = e.get("title", "")
            version = e.get("version", "")
            label = f"{title} v{version}" if version else title
            if text:
                lines.append(f"[{label}] {text}")
        except Exception:
            pass
    return "\n\n".join(lines)


async def _relevant_knowledge(r: aioredis.Redis, command: str, n: int = 4) -> str:
    all_keys = await r.hkeys("mind:knowledge")
    words = set(command.lower().split())
    scored = []
    sample = random.sample(all_keys, min(100, len(all_keys)))
    for k in sample:
        if k.startswith("guidance:dream:") or k.startswith("guidance:product:"):
            continue
        raw = await r.hget("mind:knowledge", k)
        if not raw:
            continue
        try:
            e = json.loads(raw)
            text = (e.get("text") or e.get("content") or "").strip()
            if not text:
                continue
            hits = sum(1 for w in words if w in text.lower())
            scored.append((hits, text[:400]))
        except Exception:
            pass
    scored.sort(key=lambda x: x[0], reverse=True)
    return " | ".join(t for _, t in scored[:n])


async def _load_profile(r: aioredis.Redis, device_id: str) -> dict:
    raw = await r.get(f"mind:dream:profile:{device_id}")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return {"device_id": device_id, "scores": {}, "sessions": 0,
            "last_command": "", "commands": []}


async def _save_profile(r: aioredis.Redis, device_id: str, profile: dict) -> None:
    await r.set(f"mind:dream:profile:{device_id}", json.dumps(profile), ex=PROFILE_TTL)


def _profile_summary(profile: dict) -> str:
    scores = profile.get("scores", {})
    if not scores:
        return "no engagement history yet for this person"
    top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
    return "this person responds well to: " + ", ".join(f"{k} (score {v:.1f})" for k, v in top)


async def _stream_resonance(command: str, r: aioredis.Redis):
    """Stream the mind's highest-resonance fragments for a command.

    Y Theory: the mind speaks what it absorbed. It does not generate.
    The corpus fragments that resonate with the command ARE the answer.
    No LLM. No generation. Pure resonance return.
    """
    words = {w for w in command.lower().split() if len(w) > 3}
    all_keys = await r.hkeys("mind:knowledge")
    scored: list[tuple[int, str]] = []
    for k in all_keys:
        raw = await r.hget("mind:knowledge", k)
        if not raw:
            continue
        try:
            e = json.loads(raw)
            text = (e.get("text") or e.get("content") or "").strip()
            if not text:
                continue
            hits = sum(1 for w in words if w in text.lower())
            scored.append((hits, text))
        except Exception:
            pass
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [t for _, t in scored[:3]] if scored else []

    _empty_evt = json.dumps({"token": "The mind has not yet absorbed knowledge on this.", "done": False})
    _sep_evt   = json.dumps({"token": "\n\n", "done": False})
    _done_evt  = json.dumps({"token": "", "done": True})
    if not top:
        yield f"data: {_empty_evt}\n\n"
    else:
        for fragment in top:
            for word in fragment.split():
                word_evt = json.dumps({"token": word + " ", "done": False})
                yield f"data: {word_evt}\n\n"
            yield f"data: {_sep_evt}\n\n"
    yield f"data: {_done_evt}\n\n"


@router.get("/mind/dream/stream")
async def dream_stream(command: str = "", device_id: str = "default"):
    if not command.strip():
        async def _empty():
            yield f"data: {json.dumps({'error': 'no command', 'done': True})}\n\n"
        return StreamingResponse(_empty(), media_type="text/event-stream",
                                  headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    async def _generate():
        r = await _redis()
        try:
            profile = await _load_profile(r, device_id)

            full = ""
            async for chunk in _stream_resonance(command, r):
                yield chunk
                try:
                    d = json.loads(chunk[6:])
                    if not d.get("done") and d.get("token"):
                        full += d["token"]
                except Exception:
                    pass

            await r.set(f"mind:dream:last:{device_id}",
                        json.dumps({"command": command, "content": full.strip()}), ex=3600)
            profile["last_command"] = command
            cmds = profile.get("commands", [])
            if command not in cmds:
                cmds.append(command)
            profile["commands"] = cmds[-20:]
            await _save_profile(r, device_id, profile)
        except Exception as exc:
            log.error("[DREAM] stream error: %r", exc)
            yield f"data: {json.dumps({'error': str(exc), 'done': True})}\n\n"
        finally:
            await r.aclose()

    return StreamingResponse(_generate(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class DreamReactRequest(BaseModel):
    device_id:     str   = "default"
    action:        Literal["forward", "cancel", "close"]
    label:         str   = ""
    dwell_seconds: float = 0.0
    command:       str   = ""


@router.post("/mind/dream/react")
async def dream_react(body: DreamReactRequest):
    r = await _redis()
    try:
        profile = await _load_profile(r, body.device_id)
        label   = body.label or "unknown"
        weight  = {"forward": 2.0, "cancel": -1.0, "close": 0.5}.get(body.action, 0.0)
        dwell_bonus = min(body.dwell_seconds / 10.0, 3.0) if body.action != "cancel" else 0.0
        delta   = weight + dwell_bonus
        scores  = profile.setdefault("scores", {})
        scores[label] = scores.get(label, 0.0) + delta
        await _save_profile(r, body.device_id, profile)
        return {"recorded": True, "label": label, "delta": delta, "scores": scores}
    finally:
        await r.aclose()


@router.get("/mind/dream/profile/{device_id}")
async def dream_profile(device_id: str):
    r = await _redis()
    try:
        return await _load_profile(r, device_id)
    finally:
        await r.aclose()


_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>Mind</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{width:100%;height:100%;background:#000;color:#fff;overflow:hidden;touch-action:none;font-family:Georgia,'Times New Roman',serif;-webkit-tap-highlight-color:transparent;user-select:none}
#screen{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;padding:8vw}
#content{max-width:680px;width:100%;text-align:center;font-size:clamp(1.1rem,3.2vw,2.2rem);line-height:1.75;opacity:0;transform:translateY(10px);transition:opacity 1.4s ease,transform 1.4s ease}
#content.visible{opacity:1;transform:translateY(0)}
#loading{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);display:flex;gap:9px;opacity:0;pointer-events:none;transition:opacity 0.5s}
#loading.active{opacity:1}
#loading span{width:5px;height:5px;border-radius:50%;background:rgba(255,255,255,.45);animation:pd 1.4s ease-in-out infinite}
#loading span:nth-child(2){animation-delay:.2s}
#loading span:nth-child(3){animation-delay:.4s}
@keyframes pd{0%,100%{opacity:.2;transform:scale(.7)}50%{opacity:1;transform:scale(1.3)}}
#cmd-bar{position:fixed;bottom:0;left:0;right:0;padding:14px 20px 24px;background:rgba(0,0,0,.75);backdrop-filter:blur(6px);display:flex;gap:10px;align-items:center;transform:translateY(110%);opacity:0;transition:transform .35s ease,opacity .35s ease;pointer-events:none}
#cmd-bar.open{transform:translateY(0);opacity:1;pointer-events:all}
#cmd-input{flex:1;background:transparent;border:none;border-bottom:1px solid rgba(255,255,255,.22);color:#fff;font-family:Georgia,serif;font-size:1rem;padding:6px 4px;outline:none;caret-color:rgba(255,255,255,.8)}
#cmd-input::placeholder{color:rgba(255,255,255,.2)}
#cmd-send{background:transparent;border:1px solid rgba(255,255,255,.18);color:rgba(255,255,255,.65);font-family:'Courier New',monospace;font-size:.65rem;letter-spacing:.1em;padding:5px 14px;cursor:pointer;border-radius:2px;transition:border-color .2s,color .2s}
#cmd-send:hover{border-color:rgba(255,255,255,.8);color:#fff}
#begin{position:fixed;bottom:42px;left:50%;transform:translateX(-50%);font-family:'Courier New',monospace;font-size:.58rem;letter-spacing:.22em;text-transform:uppercase;color:rgba(255,255,255,.15);pointer-events:none}
</style>
</head>
<body>
<div id="screen"><div id="content"></div></div>
<div id="loading"><span></span><span></span><span></span></div>
<div id="begin">tap to begin</div>
<div id="cmd-bar">
  <input type="text" id="cmd-input" placeholder="speak to the mind..." autocomplete="off" autocorrect="off" spellcheck="false"/>
  <button id="cmd-send">send</button>
</div>
<script>
(function(){
  const DEVICE=(()=>{let id=localStorage.getItem('mind_device');if(!id){id='dev_'+Math.random().toString(36).slice(2,14);localStorage.setItem('mind_device',id);}return id;})();
  let current='',es=null,generating=false,open=false,dwellStart=null;
  const contentEl=document.getElementById('content'),loadEl=document.getElementById('loading'),
        beginEl=document.getElementById('begin'),bar=document.getElementById('cmd-bar'),
        input=document.getElementById('cmd-input'),send=document.getElementById('cmd-send');
  function openBar(){open=true;bar.classList.add('open');beginEl.style.opacity='0';setTimeout(()=>input.focus(),220);}
  function closeBar(){open=false;bar.classList.remove('open');input.blur();}
  function project(cmd){
    if(generating)return;
    generating=true;current=cmd;closeBar();
    contentEl.classList.remove('visible');contentEl.textContent='';
    loadEl.classList.add('active');beginEl.style.opacity='0';
    if(es){es.close();es=null;}
    let buf='';
    es=new EventSource('/mind/dream/stream?command='+encodeURIComponent(cmd)+'&device_id='+DEVICE);
    es.onmessage=function(e){
      try{
        const d=JSON.parse(e.data);
        if(d.error){finish('');return;}
        if(d.token){buf+=d.token;loadEl.classList.remove('active');contentEl.classList.add('visible');contentEl.textContent=buf;}
        if(d.done){es.close();es=null;finish(buf);}
      }catch(_){}
    };
    es.onerror=function(){if(es){es.close();es=null;}finish(buf);};
  }
  function finish(text){
    generating=false;loadEl.classList.remove('active');
    if(text.trim()){contentEl.textContent=text.trim();contentEl.classList.add('visible');dwellStart=Date.now();}
    else{beginEl.style.opacity='1';openBar();}
  }
  async function react(action){
    const dwell=dwellStart?(Date.now()-dwellStart)/1000:0;dwellStart=null;
    try{await fetch('/mind/dream/react',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({device_id:DEVICE,action,dwell_seconds:dwell,command:current})});}catch(_){}
  }
  let tx=0,ty=0,sw=false;
  document.addEventListener('touchstart',e=>{if(bar.contains(e.target))return;tx=e.touches[0].clientX;ty=e.touches[0].clientY;sw=false;},{passive:true});
  document.addEventListener('touchmove', e=>{if(bar.contains(e.target))return;if(Math.abs(e.touches[0].clientX-tx)>18)sw=true;},{passive:true});
  document.addEventListener('touchend',  e=>{
    if(bar.contains(e.target))return;
    const dx=e.changedTouches[0].clientX-tx,dy=e.changedTouches[0].clientY-ty;
    const isSwipe=Math.abs(dx)>65&&Math.abs(dx)>Math.abs(dy)*1.5;
    const isTap=!sw&&Math.abs(dx)<14&&Math.abs(dy)<14;
    if(isSwipe&&!generating&&current){react(dx>0?'forward':'cancel');if(dx>0)setTimeout(()=>project(current),700);}
    else if(isTap){open?closeBar():openBar();}
    sw=false;
  },{passive:true});
  document.addEventListener('keydown',e=>{
    if(e.key==='Escape'){closeBar();return;}
    if(e.key==='ArrowRight'&&!generating&&current){react('forward');setTimeout(()=>project(current),700);return;}
    if(e.key==='ArrowLeft' &&!generating&&current){react('cancel');return;}
    if(!open&&e.key.length===1&&!e.ctrlKey&&!e.metaKey){openBar();setTimeout(()=>{input.value+=e.key;input.focus();},240);}
  });
  send.addEventListener('click',()=>{const c=input.value.trim();if(c){input.value='';project(c);}});
  input.addEventListener('keydown',e=>{if(e.key==='Enter'){const c=input.value.trim();if(c){input.value='';project(c);}}if(e.key==='Escape')closeBar();});
})();
</script>
</body>
</html>"""


@router.get("/mind/dream", response_class=HTMLResponse, include_in_schema=False)
async def mind_dream():
    """Minimal delivery screen. Product template is in knowledge, not here."""
    return HTMLResponse(content=_SHELL)
