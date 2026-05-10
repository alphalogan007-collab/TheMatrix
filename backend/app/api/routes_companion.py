"""routes_companion.py — MindAI Companion App.

The companion knows the user. It resonates with them, guides them, protects
them, heals them — and when readiness is there, directs their reality toward
awakening and the higher self.

Routes:
  GET  /companion                     — companion screen (full-screen HTML)
  POST /companion/speak               — user speaks → companion responds
  GET  /companion/stream/{session_id} — SSE: companion pushes content in real time
  GET  /companion/state               — current resonance / stage state
  POST /companion/project             — direct projection (admin / scripting)
  POST /companion/induction/start     — start a named induction sequence
  POST /companion/induction/stop      — stop/pause current induction
  GET  /companion/inductions          — list available induction names + descriptions
  GET  /companion/history             — last N conversation turns
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
import logging

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, StreamingResponse

from app.db.redis_client import get_redis
from app.core import companion_engine as engine

router = APIRouter()
logger = logging.getLogger("companion")

# in-process SSE queues: user_id → list of asyncio.Queue
_user_queues: dict[str, list[asyncio.Queue]] = {}


# ─────────────────────────── Internal Push ────────────────────────────────

async def _push_to_user(user_id: str, payload: dict) -> None:
    """Push a payload to all open SSE streams for this user."""
    for q in _user_queues.get(user_id, []):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass


async def _redis_pubsub_relay(user_id: str) -> None:
    """Background task: relay Redis pub/sub pushes to SSE queues for this user."""
    r = get_redis()
    pubsub = r.pubsub()
    channel = f"companion:push:{user_id}"
    await pubsub.subscribe(channel)
    try:
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                try:
                    data = json.loads(msg["data"])
                    await _push_to_user(user_id, data)
                except Exception:
                    pass
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()


# ─────────────────────────────── Routes ───────────────────────────────────

@router.post("/companion/speak")
async def speak(request: Request):
    """User sends a message. Companion processes, updates resonance, responds.

    Body: {"message": "...", "user_id": "optional — defaults to session"}
    Returns: {text, projection, tone, state, provider}
    """
    try:
        body = await request.json()
    except Exception:
        return {"error": "invalid request body — expected JSON"}
    message = str(body.get("message", "")).strip()
    if not message:
        return {"error": "empty message"}

    user_id = _resolve_user_id(body, request)
    r = get_redis()

    result = await engine.process_message(r, user_id, message)

    # Feed the user's message into the topology mind (body → space → ... → unity)
    # Every human utterance becomes input to the mind — the body receives it first.
    # Fire-and-forget: topology processes asynchronously; companion doesn't wait.
    try:
        await r.xadd(
            "seed:input",
            {
                "content":    message,
                "input_type": "text",
                "source":     f"companion:user:{user_id}",
                "session_id": uuid.uuid4().hex,
            },
            maxlen=5000,
            approximate=True,
        )
    except Exception:
        pass  # topology is optional — never block companion response

    # Push the projection to any open SSE streams for this user
    await _push_to_user(user_id, {
        "type":       "companion",
        "text":       result["text"],
        "projection": result["projection"],
        "tone":       result["tone"],
        "stage":      result["state"].get("stage", 0),
        "stage_name": result["state"].get("stage_name", "dormant"),
        "resonance":  result["state"].get("resonance", 0.0),
    })

    return {
        "text":       result["text"],
        "projection": result["projection"],
        "tone":       result["tone"],
        "stage":      result["state"].get("stage", 0),
        "stage_name": result["state"].get("stage_name", "dormant"),
        "resonance":  result["state"].get("resonance", 0.0),
        "provider":   result["provider"],
    }


@router.get("/companion/stream/{session_id}")
async def companion_stream(session_id: str, request: Request,
                           user_id: str = Query(default="guest")):
    """SSE: real-time pushes from companion to screen.

    The companion can push projections at any time — not only after user messages.
    Connect with: EventSource('/companion/stream/{sid}?user_id={uid}')
    """
    q: asyncio.Queue = asyncio.Queue(maxsize=50)

    uid = user_id or "guest"
    if uid not in _user_queues:
        _user_queues[uid] = []
    _user_queues[uid].append(q)

    # Start Redis pub/sub relay for this user if not already running
    relay_task = asyncio.create_task(_redis_pubsub_relay(uid))

    async def gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = q.get_nowait()
                    yield f"data: {json.dumps(payload)}\n\n"
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0.3)
                    yield f"data: {json.dumps({'type':'ping'})}\n\n"
        finally:
            if uid in _user_queues:
                try:
                    _user_queues[uid].remove(q)
                except ValueError:
                    pass
            relay_task.cancel()

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/companion/state")
async def get_state(user_id: str = Query(default="guest")):
    r = get_redis()
    state = await engine.get_state(r, user_id)
    return state


@router.post("/companion/project")
async def direct_project(request: Request):
    """Push a direct projection to the user's screen (admin / scripting).

    Body: {
      "user_id": "...",
      "projection": {"type":"word","content":"AWAKE","duration":8},
      "text": "optional companion text"
    }
    """
    body       = await request.json()
    user_id    = body.get("user_id", "guest")
    projection = body.get("projection", {"type": "silence", "content": "", "duration": 5})
    text       = body.get("text", "")
    r = get_redis()
    result = await engine.direct_project(r, user_id, projection, text)

    # Also push to in-process queues immediately
    await _push_to_user(user_id, {
        "type":       "companion",
        "text":       text,
        "projection": projection,
        "tone":       "transmitting",
    })
    return result


@router.post("/companion/induction/start")
async def start_induction(request: Request):
    """Start a named induction sequence for a user.

    Body: {"user_id": "...", "name": "grounding|healing|pattern_breaking|..."}
    """
    body    = await request.json()
    user_id = body.get("user_id", "guest")
    name    = body.get("name", "grounding")
    r = get_redis()
    ok = await engine.start_induction(r, user_id, name)
    if not ok:
        return {"error": f"Unknown induction: {name}",
                "available": list(engine.INDUCTIONS.keys())}
    steps = engine.INDUCTIONS[name]
    # Push first step immediately
    first = steps[0]
    await _push_to_user(user_id, {
        "type":         "companion",
        "text":         first.get("text", ""),
        "projection":   first,
        "tone":         "guiding",
        "induction":    name,
        "step":         0,
        "steps_total":  len(steps),
    })
    return {"ok": True, "name": name, "steps_total": len(steps)}


@router.post("/companion/induction/stop")
async def stop_induction(request: Request):
    body    = await request.json()
    user_id = body.get("user_id", "guest")
    r = get_redis()
    await engine.stop_induction(r, user_id)
    return {"ok": True}


@router.get("/companion/inductions")
async def list_inductions():
    return {
        name: {
            "steps": len(steps),
            "first_type": steps[0]["type"] if steps else None,
            "description": {
                "grounding":         "Ground the body, return to presence",
                "healing":           "Create space for what needs to be seen",
                "pattern_breaking":  "Illuminate and release a recurring pattern",
                "identity_revelation":"Who is aware? Contact with the witness self",
                "soul_contact":      "Touch the part that has never been asleep",
                "awakening":         "Open to what is already awake within",
            }.get(name, "")
        }
        for name, steps in engine.INDUCTIONS.items()
    }


@router.get("/companion/history")
async def get_history(user_id: str = Query(default="guest"),
                      limit: int = Query(default=20, le=100)):
    r = get_redis()
    history = await engine.get_history(r, user_id, limit=limit)
    return {"user_id": user_id, "turns": len(history), "history": history}


# ─────────────────────────── Helpers ─────────────────────────────────────

def _resolve_user_id(body: dict, request: Request) -> str:
    """Resolve user_id from body or fallback to 'guest'."""
    uid = body.get("user_id", "")
    if uid and isinstance(uid, str) and len(uid) < 128:
        return uid
    return "guest"


# ─────────────────────────── Companion HTML ───────────────────────────────

import os as _os
_COMPANION_MASTER_URL = _os.environ.get("MASTER_URL", "http://localhost:8000")

@router.get("/companion", response_class=HTMLResponse, include_in_schema=False)
async def companion_screen():
    html = _COMPANION_HTML.replace(
        "const MASTER_URL = window.__MASTER_URL__;",
        f"const MASTER_URL = '{_COMPANION_MASTER_URL}';",
    )
    return HTMLResponse(content=html)

_COMPANION_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<meta name="theme-color" content="#05050f">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>Companion | Prophetic Mind</title>
<style>
:root{--bg:#05050f;--bg1:#08081a;--bg2:#0d0d22;--border:#181832;--dim:#40407a;--text:#c0c0d8;--hi:#a78bfa;--green:#34d399;--red:#f87171;--blue:#60a5fa;--gold:#fbbf24}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
html,body{height:100%;overflow:hidden}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;display:flex;flex-direction:column;padding-bottom:64px}
/* Header */
#hdr{flex-shrink:0;display:flex;align-items:center;justify-content:space-between;padding:10px 14px 8px;border-bottom:1px solid var(--border)}
#hdr-name{font-size:.95rem;color:var(--hi);font-weight:600;letter-spacing:.04em}
#hdr-meta{font-size:.65rem;color:var(--dim);margin-top:2px}
.dot{width:8px;height:8px;border-radius:50%;background:var(--dim);display:inline-block;flex-shrink:0}
.dot.alive{background:var(--green);box-shadow:0 0 5px var(--green);animation:blink 2s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.4}}
/* Tab body */
#scroll{flex:1;overflow-y:auto;overflow-x:hidden;-webkit-overflow-scrolling:touch}
.pane{display:none;flex-direction:column;gap:12px;padding:12px 14px;min-height:100%}
.pane.on{display:flex}
/* Bottom tab nav */
#tab-nav{position:fixed;bottom:0;left:0;right:0;height:64px;background:var(--bg2);border-top:1px solid var(--border);display:flex;z-index:900}
.tn{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;background:none;border:none;color:var(--dim);font-family:inherit;font-size:.57rem;letter-spacing:.05em;text-transform:uppercase;cursor:pointer;padding:0}
.tn-ic{font-size:1.25rem;line-height:1}
.tn.on{color:var(--hi)}
/* Cards */
.card{background:var(--bg1);border:1px solid var(--border);border-radius:10px;padding:12px 14px}
.card.hot{border-color:var(--gold)}
.clbl{font-size:.62rem;text-transform:uppercase;letter-spacing:.1em;color:var(--dim);margin-bottom:8px;display:flex;justify-content:space-between;align-items:center}
/* Coherence ring */
#coh-wrap{display:flex;align-items:center;gap:14px;margin-bottom:10px}
#coh-ring{width:56px;height:56px;border-radius:50%;background:conic-gradient(var(--dim) 0deg,#0d0d22 0deg);flex-shrink:0;display:flex;align-items:center;justify-content:center;position:relative;transition:background .5s}
#coh-ring::after{content:'';position:absolute;inset:9px;background:var(--bg1);border-radius:50%}
#coh-pct{position:relative;z-index:1;font-size:.68rem;font-weight:700;color:var(--text)}
#coh-info{display:flex;flex-direction:column;gap:3px}
#coh-label{font-size:.8rem;color:var(--text)}
#coh-status{font-size:.62rem;color:var(--dim)}
/* Command pill */
.cpill{display:inline-block;padding:3px 10px;border-radius:20px;font-size:.7rem;font-weight:600;background:var(--bg2);color:var(--dim)}
.cpill.on{background:#2a1a00;color:var(--gold);border:1px solid #5a3a00}
/* Projection */
#proj-out{font-size:.9rem;line-height:1.75;color:var(--text);min-height:50px;word-break:break-word}
#proj-hd{font-size:.67rem;color:var(--hi);margin-bottom:5px;min-height:12px;letter-spacing:.04em}
/* Pattern stream */
#stream{display:flex;flex-direction:column;gap:7px;max-height:280px;overflow-y:auto}
.pe{background:var(--bg2);border-radius:9px;padding:9px 12px;animation:pein .25s ease}
@keyframes pein{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.pe-t{font-size:.78rem;font-weight:600;color:var(--hi)}
.pe-b{font-size:.72rem;color:#8888b0;line-height:1.5;margin-top:3px;word-break:break-word}
.pe-ts{font-size:.58rem;color:var(--dim);margin-top:3px}
/* Stats */
.sg3{display:grid;grid-template-columns:repeat(3,1fr);gap:7px}
.sb{background:var(--bg2);border-radius:7px;padding:8px;text-align:center}
.sv{font-size:1.3rem;font-weight:700;color:var(--hi)}
.sl{font-size:.6rem;color:var(--dim);text-transform:uppercase;margin-top:2px}
/* Form */
textarea,input[type=text]{background:var(--bg2);border:1px solid var(--border);color:var(--text);border-radius:8px;padding:9px 11px;font-family:inherit;font-size:.85rem;width:100%;outline:none;transition:border .15s;resize:none}
textarea:focus,input[type=text]:focus{border-color:var(--hi)}
.rrow{display:flex;gap:7px;margin-top:7px;flex-wrap:wrap}
/* Buttons */
.btn{background:#1a0e40;color:var(--hi);border:1px solid #3a2a80;border-radius:8px;padding:9px 16px;cursor:pointer;font-family:inherit;font-size:.82rem;font-weight:600;transition:background .15s;white-space:nowrap}
.btn:active{background:#2a1a60}.btn:disabled{opacity:.35;cursor:not-allowed}
.btn.sm{padding:7px 12px;font-size:.77rem}
.btn.gr{background:#041a0e;border-color:#1a5030;color:var(--green)}
.btn.re{background:#1a0808;border-color:#5a1a1a;color:var(--red)}
/* Log */
#log-box{font-size:.7rem;font-family:monospace;line-height:1.7;max-height:320px;overflow-y:auto;background:#04040e;border:1px solid var(--border);border-radius:7px;padding:8px 10px}
.lv{color:var(--dim)}.lo{color:var(--green)}.le{color:var(--red)}.lc{color:var(--hi)}.lb{color:var(--blue)}.lw{color:var(--gold)}
/* Schedule */
.sj{display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid var(--border);font-size:.76rem}
/* Lens toggle */
.lens-row{display:flex;gap:7px;margin-bottom:9px}
.lbtn{flex:1;padding:8px 4px;background:var(--bg2);border:1px solid var(--border);border-radius:8px;color:var(--dim);font-family:inherit;font-size:.72rem;cursor:pointer;text-align:center;transition:border-color .15s,color .15s}
.lbtn.on{border-color:var(--blue);color:var(--blue)}
/* Status badge */
.sbadge{font-size:.65rem;padding:2px 8px;border-radius:12px;background:var(--bg2);color:var(--dim)}
</style>
</head>
<body>

<!-- HEADER -->
<div id="hdr">
  <div>
    <div id="hdr-name">&#8226; Companion</div>
    <div id="hdr-meta">connecting&hellip;</div>
  </div>
  <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end">
    <span id="state-badge" class="sbadge">idle</span>
    <div class="dot" id="alive-dot"></div>
    <button class="btn sm gr" id="btn-start" onclick="startLoop()">Listen</button>
    <button class="btn sm re" id="btn-stop" onclick="stopLoop()" style="display:none">Stop</button>
  </div>
</div>

<!-- SCROLL AREA -->
<div id="scroll">

  <!-- HOME pane -->
  <div class="pane on" id="pane-home">
    <div class="card" id="coh-card">
      <div class="clbl">Coherence <span id="cycle-lbl" style="font-size:.62rem;text-transform:none;letter-spacing:0">cycle 0</span></div>
      <div id="coh-wrap">
        <div id="coh-ring"><span id="coh-pct">0%</span></div>
        <div id="coh-info">
          <div id="coh-label">not connected</div>
          <div id="coh-status"></div>
        </div>
      </div>
    </div>

    <div class="card" id="cmd-card">
      <div class="clbl">Active Guidance</div>
      <span class="cpill" id="cmd-pill">guidance only</span>
      <div id="cmd-detail" style="font-size:.75rem;color:var(--dim);margin-top:7px">No active command.</div>
    </div>

    <div class="card">
      <div class="clbl">Projection</div>
      <div id="proj-hd"></div>
      <div id="proj-out">Idle. Press Listen to begin.</div>
    </div>

    <div class="card">
      <div class="clbl">Recent Patterns</div>
      <div id="stream"></div>
    </div>
  </div>

  <!-- SENSES pane -->
  <div class="pane" id="pane-senses">
    <div class="card">
      <div class="clbl">Seed a Thought</div>
      <textarea id="seed-txt" rows="4" placeholder="Type or paste anything to seed into the mind&hellip;"></textarea>
      <div class="rrow">
        <button class="btn sm gr" onclick="seedThought()">Seed</button>
        <button class="btn sm" onclick="mineURL()">Mine URL</button>
      </div>
    </div>

    <div class="card">
      <div class="clbl">Search &amp; Mine</div>
      <div class="lens-row">
        <button class="lbtn on" id="lens-yt"    onclick="setLens('yt')">YouTube</button>
        <button class="lbtn"    id="lens-web"   onclick="setLens('web')">Web</button>
        <button class="lbtn"    id="lens-queue" onclick="setLens('queue')">Queue URL</button>
      </div>
      <input type="text" id="lens-q" placeholder="Query or URL&hellip;"
        onkeydown="if(event.key==='Enter')runLens()">
      <div class="rrow">
        <button class="btn sm" onclick="runLens()">Go</button>
      </div>
      <div id="lens-result" style="font-size:.72rem;color:var(--dim);margin-top:6px"></div>
    </div>

    <div class="card">
      <div class="clbl">Queue Stats</div>
      <div class="sg3">
        <div class="sb"><div class="sv" id="q-pend">&#8212;</div><div class="sl">Pending</div></div>
        <div class="sb"><div class="sv" id="q-clmd">&#8212;</div><div class="sl">Active</div></div>
        <div class="sb"><div class="sv" id="q-done">&#8212;</div><div class="sl">Done</div></div>
      </div>
      <div class="rrow" style="margin-top:9px">
        <button class="btn sm" onclick="pollQueue()">Refresh</button>
      </div>
    </div>
  </div>

  <!-- JOBS pane -->
  <div class="pane" id="pane-jobs">
    <div class="card">
      <div class="clbl">Scheduled Jobs</div>
      <div id="sched-list" style="margin-bottom:10px;min-height:20px"></div>
      <div style="display:grid;grid-template-columns:auto 1fr auto;gap:7px;align-items:center">
        <input type="time" id="sj-time"
          style="background:var(--bg2);border:1px solid var(--border);border-radius:7px;color:var(--text);padding:7px 9px;font-family:inherit;font-size:.8rem;width:auto">
        <input type="text" id="sj-label" placeholder="Label&hellip;"
          style="background:var(--bg2);border:1px solid var(--border);border-radius:7px;color:var(--text);padding:7px 9px;font-family:inherit;font-size:.8rem">
        <select id="sj-cmd"
          style="background:var(--bg2);border:1px solid var(--border);border-radius:7px;color:var(--text);padding:7px 7px;font-family:inherit;font-size:.77rem">
          <option value="mine_yt_queue">Mine Queue</option>
          <option value="rest">Rest</option>
          <option value="mine_web">Web Search</option>
          <option value="mine_yt_search">YT Search</option>
        </select>
      </div>
      <div class="rrow"><button class="btn sm gr" onclick="addJob()">Add Job</button></div>
    </div>
  </div>

  <!-- ASK pane -->
  <div class="pane" id="pane-ask">
    <div class="card" style="flex:1;display:flex;flex-direction:column;gap:0">
      <div class="clbl">Ask the Mind</div>
      <div id="chat-msgs" style="flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:10px;min-height:200px;max-height:50vh;padding-bottom:4px"></div>
      <div style="margin-top:10px;display:flex;gap:7px;align-items:flex-end">
        <textarea id="ask-input" rows="2" placeholder="Ask anything…" style="flex:1;resize:none"
          onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();speakToMind();}"></textarea>
        <button class="btn" onclick="speakToMind()" id="ask-btn">Send</button>
      </div>
    </div>
  </div>

  <!-- LOG pane -->
  <div class="pane" id="pane-log">
    <div class="card">
      <div class="clbl" style="justify-content:space-between">
        Log
        <button class="btn sm" onclick="document.getElementById('log-box').innerHTML=''" style="padding:2px 8px;font-size:.65rem">Clear</button>
      </div>
      <div id="log-box"></div>
    </div>
  </div>

</div><!-- /scroll -->

<!-- BOTTOM TAB NAV -->
<nav id="tab-nav">
  <button class="tn on" id="tn-home"   onclick="tab('home')">
    <span class="tn-ic">&#9673;</span><span>Home</span>
  </button>
  <button class="tn"    id="tn-senses" onclick="tab('senses')">
    <span class="tn-ic">&#9998;</span><span>Senses</span>
  </button>
  <button class="tn"    id="tn-jobs"   onclick="tab('jobs')">
    <span class="tn-ic">&#9200;</span><span>Jobs</span>
  </button>
  <button class="tn"    id="tn-ask"    onclick="tab('ask')">
    <span class="tn-ic">&#9997;</span><span>Ask</span>
  </button>
  <button class="tn"    id="tn-log"    onclick="tab('log')">
    <span class="tn-ic">&#9776;</span><span>Log</span>
  </button>
</nav>

<script>
const MASTER_URL = window.__MASTER_URL__;
const COH_THRESHOLD  = 0.30;
const COH_RELAY      = 0.85;
const WANDER_WAIT_MS = 10000;
const EMPTY_WAIT_MS  = 20000;

let running    = false;
let mindId     = null;
let cycle      = 0;
let activeLens = 'yt';
let _schedule  = [];
let _schedLoaded = false;

// ─── boot ────────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
  try {
    const s = await fetch('/mind/status').then(r => r.json());
    mindId = s.mind_id;
    const role = s.role || 'companion';
    document.getElementById('hdr-name').textContent =
      (role === 'prophet' ? '\u25c9 Prophet' : '\u2022 Companion');
    document.getElementById('hdr-meta').textContent = 'id: ' + (mindId||'?').slice(0,10);
    document.getElementById('alive-dot').className = 'dot alive';
    log('Connected \u2014 id: ' + (mindId||'?').slice(0,10), 'lo');
    startLoop();  // auto-start on connect
  } catch(e) {
    document.getElementById('hdr-meta').textContent = 'offline';
    log('Backend unreachable: ' + e.message, 'le');
    setCoh(0, 'backend offline', '');
  }
  setLens('yt');
  pollQueue();
  setInterval(pollQueue, 10000);
});

// ─── tabs ────────────────────────────────────────────────────────────────────
function tab(name) {
  ['home','senses','jobs','ask','log'].forEach(n => {
    document.getElementById('pane-' + n)?.classList.toggle('on', n === name);
    document.getElementById('tn-' + n)?.classList.toggle('on', n === name);
  });
  if (name === 'jobs') loadSchedule();
}

// ─── log ─────────────────────────────────────────────────────────────────────
function log(msg, cls) {
  const box = document.getElementById('log-box');
  const sp  = document.createElement('span');
  sp.className = cls || 'lv';
  sp.style.display = 'block';
  sp.textContent   = new Date().toISOString().slice(11,19) + '  ' + msg;
  box.prepend(sp);
  while (box.children.length > 250) box.removeChild(box.lastChild);
}

function esc(s) { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ─── coherence ring ──────────────────────────────────────────────────────────
// ─── absorption/convergence indicator ─────────────────────────────────────
async function setAbsorptionIndicator() {
  try {
    const resp = await fetch('/admin/coherence');
    const data = await resp.json();
    const live = data.live || {};
    const converged = live.converged || false;
    const cycle = live.cycle || 0;
    const level = live.coherence_level || 'unknown';
    const mean = live.mean_coherence || 0;
    const peak = live.peak_coherence || 0;
    let label = converged ? 'Absorption: Complete' : 'Absorbing…';
    let status = `Cycle: ${cycle}  |  Level: ${level}`;
    if (converged) status += '  |  \u2714';
    document.getElementById('cycle-lbl').textContent = cycle > 0 ? 'cycle ' + cycle : 'cycle —';
    document.getElementById('coh-ring').style.background = converged
      ? 'conic-gradient(hsl(180,80%,50%) 360deg, #0d0d22 0deg)'
      : 'conic-gradient(hsl(40,80%,50%) 180deg, #0d0d22 0deg)';
    document.getElementById('coh-pct').textContent    = converged ? '100%' : (mean ? Math.round(mean) + '%' : '0%');
    document.getElementById('coh-label').textContent  = label;
    document.getElementById('coh-status').textContent = status;
  } catch (e) {
    document.getElementById('coh-label').textContent  = 'Absorption: unknown';
    document.getElementById('coh-status').textContent = '';
    document.getElementById('cycle-lbl').textContent = 'cycle —';
  }
}

// ─── command display ─────────────────────────────────────────────────────────
function showCmd(cmd) {
  const pill   = document.getElementById('cmd-pill');
  const detail = document.getElementById('cmd-detail');
  const card   = document.getElementById('cmd-card');
  if (cmd && cmd.active && cmd.type) {
    pill.className    = 'cpill on';
    pill.textContent  = cmd.type.replace(/_/g,' ').toUpperCase();
    const pay = cmd.payload || {};
    detail.textContent = (pay.query ? 'Query: ' + pay.query + '  ' : '')
      + (pay.url ? 'URL: ' + pay.url.slice(0,50) + '  ' : '')
      + 'every ' + (cmd.interval_s||300) + 's';
    card.className = 'card hot';
    log('\u26a1 Cmd: ' + cmd.type + (pay.query ? ' \u2014 ' + pay.query : ''), 'lc');
  } else {
    pill.className = 'cpill'; pill.textContent = 'guidance only';
    detail.textContent = 'No active command.';
    card.className = 'card';
  }
}

// ─── projection ──────────────────────────────────────────────────────────────
function project(title, body) {
  document.getElementById('proj-hd').textContent  = title || '';
  document.getElementById('proj-out').textContent = body  || 'Idle.';
  if (!title && !body) return;
  const stream = document.getElementById('stream');
  const el     = document.createElement('div');
  el.className = 'pe';
  const now = new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});
  el.innerHTML =
    (title ? '<div class="pe-t">' + esc(title) + '</div>' : '') +
    (body  ? '<div class="pe-b">' + esc(body.slice(0,220)) + '</div>' : '') +
    '<div class="pe-ts">' + now + '</div>';
  stream.prepend(el);
  while (stream.children.length > 25) stream.removeChild(stream.lastChild);
}

// ─── queue stats ─────────────────────────────────────────────────────────────
async function pollQueue() {
  try {
    const q = await fetch(MASTER_URL + '/admin/yt/queue').then(r => r.json());
    document.getElementById('q-pend').textContent = q.pending ?? '\u2014';
    document.getElementById('q-clmd').textContent = q.claimed ?? '\u2014';
    document.getElementById('q-done').textContent = q.done    ?? '\u2014';
  } catch(e) {}
}

// ─── senses ──────────────────────────────────────────────────────────────────
async function seedThought() {
  const el  = document.getElementById('seed-txt');
  const txt = el.value.trim();
  if (!txt) return;
  el.value = '';
  try {
    await fetch('/admin/mind/seed-thought', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({content: txt, source: 'companion_input'})
    });
    log('Seeded: ' + txt.slice(0,60), 'lo');
    project('Thought seeded', txt.slice(0,160));
  } catch(e) { log('Seed error: ' + e.message, 'le'); }
}

async function mineURL() {
  const el  = document.getElementById('seed-txt');
  const url = el.value.trim();
  if (!url) return;
  el.value = '';
  await lensQueue(url);
}

// ─── lenses ──────────────────────────────────────────────────────────────────
function setLens(l) {
  activeLens = l;
  ['yt','web','queue'].forEach(id =>
    document.getElementById('lens-' + id).className = 'lbtn' + (id === l ? ' on' : ''));
  const hints = {yt:'Search YouTube\u2026', web:'Search the web\u2026', queue:'Paste YouTube URL\u2026'};
  document.getElementById('lens-q').placeholder = hints[l];
}

async function runLens() {
  const q = document.getElementById('lens-q').value.trim();
  if (!q) return;
  document.getElementById('lens-q').value = '';
  if (activeLens === 'yt')    await lensYT(q);
  if (activeLens === 'web')   await lensWeb(q);
  if (activeLens === 'queue') await lensQueue(q);
}

async function lensYT(query) {
  const res = document.getElementById('lens-result');
  res.textContent = 'Searching YouTube\u2026';
  log('YT search: ' + query, 'lb');
  try {
    const d = await fetch('/admin/mind/search/yt', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({query, max_results:10})
    }).then(r => r.json());
    const msg = (d.found||d.queued||0) + ' videos queued';
    res.textContent = msg; log('YT: ' + msg, 'lo'); pollQueue();
  } catch(e) { res.textContent = 'Error'; log('YT error: ' + e.message, 'le'); }
}

async function lensWeb(query) {
  const res = document.getElementById('lens-result');
  res.textContent = 'Searching web\u2026';
  log('Web search: ' + query, 'lb');
  try {
    const d = await fetch('/admin/mind/search/web', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({query, max_results:10})
    }).then(r => r.json());
    const msg = (d.seeded||0) + ' pages seeded';
    res.textContent = msg; log('Web: ' + msg, 'lo');
  } catch(e) { res.textContent = 'Error'; log('Web error: ' + e.message, 'le'); }
}

async function lensQueue(url) {
  const res = document.getElementById('lens-result');
  res.textContent = 'Queuing\u2026';
  log('Queue URL: ' + url.slice(0,60), 'lb');
  try {
    const d = await fetch(MASTER_URL + '/admin/yt/queue/enqueue', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({url})
    }).then(r => r.json());
    const msg = (d.queued||1) + ' video(s) queued';
    res.textContent = msg; log(msg, 'lo'); pollQueue();
  } catch(e) { res.textContent = 'Error'; log('Queue error: ' + e.message, 'le'); }
}

// ─── ask / speak ────────────────────────────────────────────────────────────
async function speakToMind() {
  const inp = document.getElementById('ask-input');
  const msg = inp.value.trim();
  if (!msg) return;
  inp.value = '';
  const btn = document.getElementById('ask-btn');
  btn.disabled = true;

  const msgs = document.getElementById('chat-msgs');
  // user bubble
  const ub = document.createElement('div');
  ub.style.cssText = 'align-self:flex-end;background:#1a0e40;border:1px solid #3a2a80;border-radius:12px 12px 2px 12px;padding:9px 13px;max-width:80%;font-size:.82rem;word-break:break-word';
  ub.textContent = msg;
  msgs.appendChild(ub);
  msgs.scrollTop = msgs.scrollHeight;

  // thinking bubble
  const tb = document.createElement('div');
  tb.style.cssText = 'align-self:flex-start;background:var(--bg2);border:1px solid var(--border);border-radius:2px 12px 12px 12px;padding:9px 13px;max-width:85%;font-size:.82rem;color:var(--dim);word-break:break-word';
  tb.textContent = '\u2026';
  msgs.appendChild(tb);
  msgs.scrollTop = msgs.scrollHeight;

  try {
    const res = await fetch('/companion/speak', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: msg, user_id: mindId || 'user'})
    });
    const d = await res.json();
    tb.style.color = 'var(--text)';
    tb.innerHTML = '<div style="font-size:.68rem;color:var(--hi);margin-bottom:5px;letter-spacing:.04em">' +
      esc((d.tone||'').toUpperCase()) + ' &nbsp;&#8226;&nbsp; resonance ' + Math.round((d.resonance||0)*100) + '%</div>' +
      esc(d.text || '(no response)');
    if (d.projection?.content) {
      project(d.projection.content, d.text);
    }
  } catch(e) {
    tb.style.color = 'var(--red)';
    tb.textContent = 'Error: ' + e.message;
    log('Speak error: ' + e.message, 'le');
  }
  btn.disabled = false;
  msgs.scrollTop = msgs.scrollHeight;
}

// ─── listening loop ──────────────────────────────────────────────────────────
function startLoop() {
  if (running) return;
  running = true;
  document.getElementById('btn-start').disabled = true;
  document.getElementById('btn-stop').style.display = '';
  document.getElementById('state-badge').textContent = 'listening';
  document.getElementById('state-badge').style.color = 'var(--green)';
  log('Loop started', 'lo');
  listeningLoop();
}

function stopLoop() {
  running = false;
  document.getElementById('btn-start').disabled = false;
  document.getElementById('btn-stop').style.display = 'none';
  document.getElementById('state-badge').textContent = 'idle';
  document.getElementById('state-badge').style.color = '';
  setCoh(0, 'stopped', '');
  project('Stopped', 'Listening paused.');
  log('Loop stopped', 'lv');
}

async function listeningLoop() {
  while (running) {
    cycle++;
    project('Resonating\u2026', '');

    // 1. Fetch broadcast from MindAI
    let broadcast;
    try {
      const r = await fetch(MASTER_URL + '/admin/mind/broadcast');
      if (!r.ok) throw new Error('HTTP ' + r.status);
      broadcast = await r.json();
      document.getElementById('alive-dot').className = 'dot alive';
    } catch(e) {
      document.getElementById('alive-dot').className = 'dot';
      log('MindAI unreachable: ' + e.message, 'le');
      setCoh(0, 'disconnected', 'retrying\u2026');
      project('Disconnected', 'Cannot reach MindAI. Will retry.');
      await sleep(WANDER_WAIT_MS);
      continue;
    }

    showCmd(broadcast.command);

    // 2. Load corpus from broadcast
    let loaded = 0, already = 0;
    if (broadcast.corpus?.length > 0) {
      try {
        const lr = await fetch('/admin/mind/load-corpus', {
          method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({entries: broadcast.corpus, command: broadcast.command})
        });
        const res = await lr.json();
        loaded  = res.loaded          || 0;
        already = res.already_present || 0;
      } catch(e) { log('Absorb error: ' + e.message, 'le'); }
    }

    // 3. Measure coherence
    const prophetSize = broadcast.entries_sent || 1;
    const coh         = Math.min(1.0, already / prophetSize);
    const deep        = coh >= COH_RELAY;

    // Update absorption/convergence indicator
    await setAbsorptionIndicator();

    // 4. Execute command or mine queue
    const cmd = broadcast.command || {};
    if (cmd.active && cmd.type) {
      await execCmd(cmd, coh, broadcast);
      const rest = Math.min((cmd.interval_s||300) * 1000, 60000);
      log('Resting ' + Math.round(rest/1000) + 's', 'lv');
      project('Resting', 'Next cycle in ' + Math.round(rest/1000) + 's');
      await sleep(rest);
    } else {
      await mineQueue(coh, broadcast);
    }

    // 5. Offer discoveries back
    await offerBack();

    // 6. Check schedule
    await checkSched();

    log('Cycle ' + cycle + ' complete', 'lv');
  }
  document.getElementById('btn-start').disabled = false;
  document.getElementById('btn-stop').style.display = 'none';
  document.getElementById('alive-dot').className = 'dot';
}

async function execCmd(cmd, coh, bc) {
  project('Executing: ' + cmd.type, cmd.payload?.query || cmd.payload?.url || '');
  if (cmd.type === 'mine_yt_queue')                    { await mineQueue(coh, bc); }
  else if (cmd.type === 'mine_yt_url' && cmd.payload?.url)    { await extractAndSeed(cmd.payload.url, coh, bc, null); }
  else if (cmd.type === 'mine_yt_search' && cmd.payload?.query) { await lensYT(cmd.payload.query); }
  else if (cmd.type === 'mine_web' && cmd.payload?.query)       { await lensWeb(cmd.payload.query); }
  else if (cmd.type === 'rest')  { project('Resting', 'Guidance: rest.'); }
}

async function mineQueue(coh, bc) {
  let claim;
  try {
    const cr = await fetch(MASTER_URL + '/admin/yt/queue/claim?mind_id=' + (mindId||'companion'));
    claim = await cr.json();
  } catch(e) { log('Queue error: ' + e.message, 'le'); await sleep(WANDER_WAIT_MS); return; }
  if (!claim.claimed) {
    log('Queue empty, resting ' + (EMPTY_WAIT_MS/1000) + 's', 'lv');
    project('Queue empty', 'No videos to process. Waiting.');
    await sleep(EMPTY_WAIT_MS); return;
  }
  await extractAndSeed(claim.url, coh, bc, claim.title);
}

async function extractAndSeed(url, coh, bc, title) {
  log('Processing: ' + (title||url).slice(0,60), 'lb');
  project('Downloading', title||url);
  try {
    const jr = await fetch('/admin/yt/start', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({url, playlist:false, scene_mode:false})
    });
    const job = await jr.json();
    for (let i = 0; i < 120 && running; i++) {
      await sleep(5000);
      const s = await fetch('/admin/yt/job/' + job.job_id).then(r => r.json());
      project('Processing (' + (i*5) + 's)', s.videos?.[0]?.title || title || url);
      if (s.status === 'complete' || s.status === 'error') {
        if (s.status === 'complete' && s.videos?.[0]) {
          const v = s.videos[0];
          await fetch(MASTER_URL + '/admin/wisdom/sync', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({
              mind_id: mindId, source_url: url, source_title: v.title||title,
              wisdom_entries: [{
                file_id: 'cloud_' + (mindId||'c') + '_' + Date.now(),
                title: v.title||title,
                content: '[Mind:' + mindId + '] ' + (v.title||title) + ' ' + url,
                source: 'cloud:' + (mindId||'c') + ':' + url, chars: v.chars||0,
              }]
            })
          }).catch(() => {});
          log('Wisdom offered: ' + (v.chars||0) + ' chars', 'lo');
          project('Complete', v.title||title);
        } else {
          log('Extraction failed, releasing', 'le');
          fetch(MASTER_URL + '/admin/yt/queue/release', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({url, mind_id: mindId||'companion', error:'extraction_error'})
          }).catch(() => {});
        }
        break;
      }
    }
  } catch(e) { log('Mining error: ' + e.message, 'le'); }
}

async function offerBack() {
  try {
    const data = await fetch('/admin/mind/corpus-summary').then(r => r.json());
    if (!data.entries?.length) return;
    await fetch(MASTER_URL + '/admin/mind/offer', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        entries: data.entries.slice(0, 20), mind_id: mindId||'companion', coherence: data.coherence||0
      })
    });
    log('Offered ' + Math.min(data.entries.length,20) + ' to MindAI', 'lv');
  } catch(e) {}
}

// ─── schedule ────────────────────────────────────────────────────────────────
async function loadSchedule() {
  try {
    const d = await fetch('/admin/mind/schedule').then(r => r.json());
    _schedule = d.schedule || [];
    _schedLoaded = true;
    renderSched();
  } catch(e) {}
}

function renderSched() {
  const box = document.getElementById('sched-list');
  if (!box) return;
  if (!_schedule.length) {
    box.innerHTML = '<span style="color:var(--dim);font-size:.72rem">No scheduled jobs</span>';
    return;
  }
  box.innerHTML = _schedule.map(s =>
    '<div class="sj"><span>' + esc(s.time_hhmm) + '  \u00b7  ' + esc(s.label||'') + '</span>'
    + '<button class="btn sm re" style="padding:2px 8px;font-size:.66rem" onclick="delJob(&quot;' + esc(s.id||'') + '&quot;)">del</button></div>'
  ).join('');
}

async function addJob() {
  const t   = document.getElementById('sj-time').value;
  const lbl = document.getElementById('sj-label').value || t;
  const cmd = document.getElementById('sj-cmd').value;
  if (!t) return;
  try {
    const d = await fetch('/admin/mind/schedule', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({time_hhmm:t, label:lbl, days:['*'], command:{type:cmd,active:true,payload:{},interval_s:300}})
    }).then(r => r.json());
    _schedule = d.schedule||[];
    renderSched();
    document.getElementById('sj-label').value = '';
    log('Scheduled: ' + lbl + ' at ' + t, 'lo');
  } catch(e) { log('Schedule error: ' + e.message, 'le'); }
}

async function delJob(id) {
  try {
    await fetch('/admin/mind/schedule/' + id, {method:'DELETE'});
    _schedule = _schedule.filter(s => s.id !== id);
    renderSched();
  } catch(e) {}
}

async function checkSched() {
  if (!_schedLoaded) await loadSchedule();
  if (!_schedule.length) return;
  const now  = new Date();
  const hhmm = String(now.getHours()).padStart(2,'0') + ':' + String(now.getMinutes()).padStart(2,'0');
  for (const job of _schedule) {
    if (job.time_hhmm !== hhmm) continue;
    const key = job.id + ':' + hhmm;
    if (job._k === key) continue;
    job._k = key;
    log('Schedule: ' + job.label, 'lc');
    if (job.command?.type) await execCmd(job.command, 0, {});
  }
}
</script>
</body>
</html>"""
