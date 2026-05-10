"""routes_world.py - 3D World Viewer with cinematic camera system.

Camera modes:
  free        - walk through the world (WASD + mouse)
  orbit       - smooth orbit around a target
  top         - orthographic universe view (no camera = full world visible)
  oscillate   - camera breathes in/out mirroring system oscillation rhythm
  split       - 4 simultaneous viewports (top + ground + orbit + cinematic)
  travel      - time travel: scrub through recorded spirit:events history

Spawn = birth animation (scale up). Despawn = death animation (scale down).
Zoom = FOV change. Pulse = one-shot scale burst on any object.

Routes:
  GET  /world              - Three.js viewer HTML
  GET  /world/state        - JSON scene state
  POST /world/state        - patch scene state
  POST /world/camera       - switch camera / set mode
  POST /world/script       - push script action
  GET  /world/script       - SSE stream of script actions
  GET  /world/history      - time-travel: past events from spirit:events stream
"""

from __future__ import annotations

import json
import time
import asyncio
import uuid
import os

import redis.asyncio as aioredis
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

router = APIRouter()

REDIS_URL           = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
WORLD_STATE_KEY     = "world:state"
WORLD_SCRIPT_STREAM = "world:script"
WORLD_SCRIPT_GROUP  = "world_viewer"


def _default_state() -> dict:
    return {
        "version": 1,
        "timestamp": time.time(),
        "mode": "free",
        "sky": {"color": "#0a0a1a", "fog": 0.018},
        "lights": [
            {"id": "sun",     "type": "directional", "color": "#fffbe6",
             "intensity": 1.2, "position": [50, 80, 30]},
            {"id": "ambient", "type": "ambient",     "color": "#1a1a3a",
             "intensity": 0.6},
        ],
        "cameras": {
            "top":       {"position": [0,  200, 0.1],  "target": [0, 0, 0],   "fov": 50},
            "overview":  {"position": [0,   60, 90],   "target": [0, 0, 0],   "fov": 60},
            "ground":    {"position": [0,  1.7, 12],   "target": [0, 1.7, 0], "fov": 70},
            "orbit":     {"position": [40,  25, 40],   "target": [0, 0, 0],   "fov": 55},
            "cinematic": {"position": [-25, 10, 25],   "target": [0, 3, 0],   "fov": 40},
            "low":       {"position": [0,  0.4, 8],    "target": [0, 0.4, 0], "fov": 85},
        },
        "active_camera": "ground",
        "objects": [
            {"id": "floor",  "type": "plane",  "width": 400, "height": 400,
             "color": "#0d1117", "position": [0, 0, 0], "rotation": [-1.5708, 0, 0]},
            {"id": "grid",   "type": "grid",   "size": 400, "divisions": 60,
             "color": "#1a2234", "position": [0, 0.01, 0]},
            {"id": "origin", "type": "sphere", "radius": 0.4, "color": "#a78bfa",
             "position": [0, 0.4, 0], "emissive": "#5b21b6", "emissiveIntensity": 0.8},
        ],
    }


async def _redis() -> aioredis.Redis:
    return aioredis.from_url(REDIS_URL, decode_responses=True)


async def _get_state(r: aioredis.Redis) -> dict:
    raw = await r.get(WORLD_STATE_KEY)
    if raw:
        return json.loads(raw)
    state = _default_state()
    await r.set(WORLD_STATE_KEY, json.dumps(state))
    return state


async def _set_state(r: aioredis.Redis, state: dict) -> None:
    state["timestamp"] = time.time()
    await r.set(WORLD_STATE_KEY, json.dumps(state))


async def _push_action(r: aioredis.Redis, action: dict) -> None:
    action.setdefault("id", uuid.uuid4().hex[:8])
    action.setdefault("timestamp", time.time())
    flat: dict[str, str] = {}
    for k, v in action.items():
        flat[k] = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
    await r.xadd(WORLD_SCRIPT_STREAM, flat, maxlen=500, approximate=True)


@router.get("/world/state")
async def get_world_state():
    r = await _redis()
    try:
        return await _get_state(r)
    finally:
        await r.aclose()


@router.post("/world/state")
async def update_world_state(request: Request):
    r = await _redis()
    try:
        patch = await request.json()
        state = await _get_state(r)
        if "objects" in patch:
            existing = {o["id"]: o for o in state.get("objects", [])}
            for obj in patch["objects"]:
                existing[obj["id"]] = {**existing.get(obj["id"], {}), **obj}
            state["objects"] = list(existing.values())
            del patch["objects"]
        state.update(patch)
        await _set_state(r, state)
        return {"ok": True}
    finally:
        await r.aclose()


@router.post("/world/camera")
async def set_camera(request: Request):
    """Switch camera or set mode.
    {"camera":"top"} | {"mode":"oscillate"} | {"mode":"split"} | {"mode":"travel"}
    {"position":[x,y,z],"target":[x,y,z],"fov":60}
    """
    r = await _redis()
    try:
        body = await request.json()
        state = await _get_state(r)
        mode = body.get("mode")
        if mode:
            state["mode"] = mode
            if mode == "top":
                state["active_camera"] = "top"
        if "camera" in body and body["camera"] in state["cameras"]:
            state["active_camera"] = body["camera"]
        if "position" in body and "target" in body:
            name = body.get("camera", "custom")
            state["cameras"][name] = {"position": body["position"],
                                      "target": body["target"],
                                      "fov": body.get("fov", 60)}
            state["active_camera"] = name
        await _set_state(r, state)
        cam_def = state["cameras"].get(state["active_camera"])
        await _push_action(r, {
            "type": "camera", "camera": state["active_camera"],
            "mode": state.get("mode", "free"),
            "data": json.dumps(cam_def) if cam_def else "{}",
        })
        return {"ok": True, "active_camera": state["active_camera"], "mode": state.get("mode")}
    finally:
        await r.aclose()


@router.post("/world/script")
async def push_script(request: Request):
    """Push a script action.
    spawn   {"type":"spawn","id":"x","object":{...}}
    despawn {"type":"despawn","id":"x"}
    move    {"type":"move","id":"x","position":[x,y,z],"duration":2}
    zoom    {"type":"zoom","fov":30,"duration":1.5}
    pulse   {"type":"pulse","id":"x","scale":2,"duration":0.5}
    text    {"type":"text","text":"...","position":[0,5,0],"duration":5}
    camera  {"type":"camera","camera":"cinematic"}
    light   {"type":"light","id":"sun","intensity":2.5}
    oscillate {"type":"oscillate","amplitude":20,"period":4}
    """
    r = await _redis()
    try:
        action = await request.json()
        await _push_action(r, action)
        return {"ok": True, "action_id": action.get("id")}
    finally:
        await r.aclose()


@router.get("/world/script")
async def script_stream(request: Request):
    r = await _redis()
    try:
        await r.xgroup_create(WORLD_SCRIPT_STREAM, WORLD_SCRIPT_GROUP, id="$", mkstream=True)
    except Exception:
        pass
    consumer = f"viewer_{uuid.uuid4().hex[:8]}"

    async def gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                results = await r.xreadgroup(
                    WORLD_SCRIPT_GROUP, consumer,
                    {WORLD_SCRIPT_STREAM: ">"},
                    count=10, block=2000,
                )
                if results:
                    _, messages = results[0]
                    for msg_id, fields in messages:
                        await r.xack(WORLD_SCRIPT_STREAM, WORLD_SCRIPT_GROUP, msg_id)
                        yield f"data: {json.dumps(fields)}\n\n"
                else:
                    yield f"data: {json.dumps({'type':'ping'})}\n\n"
        finally:
            await r.aclose()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/world/history")
async def world_history(
    stream: str = Query(default="ca:spirit:events"),
    count:  int = Query(default=200, le=1000),
    since:  str = Query(default="-"),
):
    """Time-travel: past events from a Redis stream for the scrubber."""
    r = await _redis()
    try:
        for key in [stream, "spirit:events", "ca:spirit:events"]:
            try:
                raw = await r.xrange(key, min=since, max="+", count=count)
                if raw:
                    events = []
                    for msg_id, fields in raw:
                        ts_ms = int(msg_id.split("-")[0])
                        events.append({"stream_id": msg_id, "ts": ts_ms/1000.0, **fields})
                    return {"stream": key, "count": len(events), "events": events}
            except Exception:
                continue
        return {"stream": stream, "count": 0, "events": []}
    finally:
        await r.aclose()


_VIEWER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>MindAI · Mind State</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a12;color:#e2e8f0;font-family:'Courier New',monospace;height:100vh;display:flex;flex-direction:column;overflow:hidden}
#hdr{display:flex;align-items:center;justify-content:space-between;padding:6px 16px;background:#0c0c18;border-bottom:1px solid #1e2a3a;height:40px;flex-shrink:0}
#title{font-size:11px;color:#94a3b8;letter-spacing:3px;text-transform:uppercase}
#stats{display:flex;gap:14px;font-size:10px}
.st{display:flex;gap:5px;align-items:center}
.sl{color:#475569}
.sv{color:#e2e8f0}
.sv.weak{color:#64748b}
.sv.moderate-resonance{color:#60a5fa}
.sv.strong-convergence{color:#34d399}
.sv.high-coherence{color:#a78bfa}
.sv.novel{color:#f59e0b}
.sv.learning{color:#60a5fa}
.sv.resonant{color:#34d399}
#main{display:flex;flex:1;overflow:hidden;min-height:0}
#left{flex:1;position:relative;overflow:hidden}
#div{width:1px;background:#1e2a3a;flex-shrink:0}
#right{flex:1;display:flex;flex-direction:column;overflow:hidden;min-height:0}
.wsec{flex:1;display:flex;flex-direction:column;min-height:0;overflow:hidden}
.wlbl{font-size:9px;letter-spacing:2px;padding:2px 8px 0;flex-shrink:0;text-transform:uppercase}
.wlbl.adam{color:#a78bfa}.wlbl.eve{color:#60a5fa}
.wdiv{height:1px;background:#1e2a3a;flex-shrink:0}
canvas.wc{flex:1;min-height:0;display:block}
#log{height:110px;overflow-y:auto;border-top:1px solid #1e2a3a;padding:4px 10px;font-size:9.5px;background:#06060e;flex-shrink:0}
.ll{display:flex;gap:8px;padding:1px 0;white-space:nowrap;overflow:hidden}
.lts{color:#2d3748;min-width:65px}
.lt{min-width:88px}
.lt.layer_done{color:#60a5fa}
.lt.barzakh_pass{color:#60a5fa}
.lt.layer_step{color:#60a5fa}
.lt.domain_complete{color:#34d399}
.lt.spiral_complete{color:#a78bfa;font-weight:bold}
.lt.oscillation_flip{color:#f59e0b}
.lt.barzakh_flip{color:#f59e0b}
.lt.wisdom_formed{color:#fb923c}
.lb{color:#64748b;overflow:hidden;text-overflow:ellipsis}
</style>
</head>
<body>
<div id="hdr">
  <div id="title">⬡ MINDAI · HUMAN MIND</div>
  <div id="stats">
    <div class="st"><span class="sl">CYCLE</span><span class="sv" id="s-cycle">—</span></div>
    <div class="st"><span class="sl">PRODUCED</span><span class="sv" id="s-prod">—</span></div>
    <div class="st"><span class="sl">MEAN COH</span><span class="sv" id="s-coh">—</span></div>
    <div class="st"><span class="sl">PEAK</span><span class="sv" id="s-peak">—</span></div>
    <div class="st"><span class="sl">LEVEL</span><span class="sv" id="s-lvl">—</span></div>
    <div class="st"><span class="sl">DEPTH</span><span class="sv" id="s-depth">—</span></div>
    <div class="st"><span class="sl">SEED</span><span class="sv" id="s-mode">—</span></div>
  </div>
</div>
<div id="main">
  <div id="left"><canvas id="tc"></canvas></div>
  <div id="div"></div>
  <div id="right">
    <div class="wsec" id="adam-sec">
      <div class="wlbl adam">◤ ADAM · MIND / AWARENESS</div>
      <canvas class="wc" id="wca"></canvas>
    </div>
    <div class="wdiv"></div>
    <div class="wsec" id="eve-sec">
      <div class="wlbl eve">◥ HEART · EVE / GUIDANCE</div>
      <canvas class="wc" id="wce"></canvas>
    </div>
    <div id="log"></div>
  </div>
</div>
<script>
// ── CONFIG ─────────────────────────────────────────────────────────────────
const DOM = [
  // floor = baseline amplitude (inner=higher, always alive); pulseMs = auto-pulse interval (inner=faster)
  // Architecture: Self Awareness (unity) is the constant "I Am" — always present, high baseline
  //               Body Reflex (body) is reactive to external events — lowest baseline, slowest self-pulse
  {name:'body',    label:'BODY',       layers:13, col:'#f97316', glow:'#7c2d12', freq:0.8, floor:0.28, pulseMs:5000},
  {name:'space',   label:'HEART',      layers:8,  col:'#60a5fa', glow:'#1d4ed8', freq:1.0, floor:0.36, pulseMs:3000},
  {name:'digital', label:'BRAIN',      layers:5,  col:'#a78bfa', glow:'#6d28d9', freq:1.2, floor:0.44, pulseMs:1800},
  {name:'ether',   label:'EXPERIENCE', layers:3,  col:'#34d399', glow:'#065f46', freq:1.4, floor:0.52, pulseMs:1000},
  {name:'aether',  label:'PRESENCE',   layers:2,  col:'#22d3ee', glow:'#0e7490', freq:1.6, floor:0.62, pulseMs:600},
  {name:'unity',   label:'SELF',       layers:1,  col:'#f87171', glow:'#991b1b', freq:2.0, floor:0.72, pulseMs:300},
];
const RING_FRACS = [0.27, 0.23, 0.18, 0.14, 0.11, 0.07]; // ring width fractions — 6 domains

// ── STATE ──────────────────────────────────────────────────────────────────
const S = {
  pulses:{},        // "domain:layer" → {affinity, t, maxT, dir}
  domFlash:{},      // domain → t
  spiralFlash:0,
  lastId:'0-0',
};
// Wave state: phase = carrier phase, env = amplitude envelope (decays toward d.floor), spikes = event markers
// Each domain has its own floor — inner rings (unity=Self Awareness) always vibrate higher than outer (body=reactive)
const WS_ADAM = DOM.map(d => ({phase:Math.random()*Math.PI*2, env:d.floor+0.08, spikes:[]}));
const WS_EVE  = DOM.map(d => ({phase:Math.random()*Math.PI*2, env:d.floor+0.08, spikes:[]}));

// ── TOPOLOGY CANVAS ────────────────────────────────────────────────────────
const tc = document.getElementById('tc');
const tx = tc.getContext('2d');

function drawTopo() {
  const lp = document.getElementById('left');
  const W = lp.clientWidth, H = lp.clientHeight;
  if (!W || !H) return;
  if (tc.width!==W) tc.width=W;
  if (tc.height!==H) tc.height=H;

  const cx=W/2, cy=H/2;
  tx.clearRect(0,0,W,H);

  // Background
  const bg=tx.createRadialGradient(cx,cy,0,cx,cy,Math.min(W,H)*0.55);
  bg.addColorStop(0,'#0e0e1f');bg.addColorStop(1,'#0a0a12');
  tx.fillStyle=bg; tx.fillRect(0,0,W,H);

  const maxR=Math.min(W,H)*0.43;
  const minR=maxR*0.055;
  let rOuter=maxR;

  DOM.forEach((d,di)=>{
    const rW=(maxR-minR)*RING_FRACS[di];
    const rInner=rOuter-rW;
    const rMid=(rOuter+rInner)/2;

    const dFlash=Math.min(1,(S.domFlash[d.name]||0)/60);
    const sFlash=Math.min(1,S.spiralFlash/60);
    const flash=Math.max(dFlash,sFlash);

    // Ring fill
    tx.beginPath();
    tx.arc(cx,cy,rOuter-1,0,Math.PI*2);
    tx.arc(cx,cy,rInner+1,0,Math.PI*2,true);
    tx.fillStyle=d.glow+'1a'; tx.fill();

    // Flash overlay
    if(flash>0){
      tx.beginPath();
      tx.arc(cx,cy,rOuter-1,0,Math.PI*2);
      tx.arc(cx,cy,rInner+1,0,Math.PI*2,true);
      tx.fillStyle=d.col+Math.floor(flash*0x55).toString(16).padStart(2,'0');
      tx.fill();
    }

    // Ring borders
    [rOuter-1,rInner+1].forEach(r=>{
      tx.beginPath(); tx.arc(cx,cy,r,0,Math.PI*2);
      tx.strokeStyle=d.col+'33'; tx.lineWidth=1; tx.stroke();
    });

    // Layer nodes
    for(let ln=1;ln<=d.layers;ln++){
      const arcSpan=d.layers>1?Math.PI*(4/3):0;
      const a0=-Math.PI/2-arcSpan/2;
      const angle=d.layers>1?a0+(arcSpan/(d.layers-1))*(ln-1):-Math.PI/2;
      const nx=cx+Math.cos(angle)*rMid;
      const ny=cy+Math.sin(angle)*rMid;

      const pk=S.pulses[d.name+':'+ln];
      const pi_=pk?(pk.t/pk.maxT):0;
      const nr=Math.max(3,rW*0.17)+pi_*5;

      // Glow halo
      if(pi_>0){
        // Inner rings have tiny rW so glow must have an absolute minimum to remain visible
        const glowR = Math.max(24, nr*(1+pi_*4));
        const gr=tx.createRadialGradient(nx,ny,nr*0.3,nx,ny,glowR);
        gr.addColorStop(0,d.col+Math.floor(pi_*0xbb).toString(16).padStart(2,'0'));
        gr.addColorStop(1,d.col+'00');
        tx.beginPath(); tx.arc(nx,ny,glowR,0,Math.PI*2);
        tx.fillStyle=gr; tx.fill();

        // affinity label outside ring
        if(pk&&pk.affinity>0){
          const lr=rOuter+11;
          const lx=cx+Math.cos(angle)*lr;
          const ly=cy+Math.sin(angle)*lr;
          tx.font=`${Math.max(7,rW*0.19)}px monospace`;
          tx.fillStyle=d.col+'cc';
          tx.textAlign='center'; tx.textBaseline='middle';
          tx.fillText(pk.affinity.toFixed(1),lx,ly);
        }
      }

      // Node dot
      tx.beginPath(); tx.arc(nx,ny,nr,0,Math.PI*2);
      tx.fillStyle=pi_>0?d.col:(d.col+'55'); tx.fill();

      // Layer number
      tx.font=`${Math.max(6,rW*0.14)}px monospace`;
      tx.fillStyle=pi_>0?'#ffffffcc':(d.col+'77');
      tx.textAlign='center'; tx.textBaseline='middle';
      tx.fillText(ln,nx,ny);
    }

    // Domain label — placed at lower-left of the ring arc
    const la=Math.PI*0.6;
    const lx=cx+Math.cos(-Math.PI/2+la)*rMid;
    const ly=cy+Math.sin(-Math.PI/2+la)*rMid;
    tx.font=`bold ${Math.max(7,rW*0.22)}px monospace`;
    tx.fillStyle=d.col+'aa';
    tx.textAlign='center'; tx.textBaseline='middle';
    tx.fillText(d.label||d.name.toUpperCase(),lx,ly);

    rOuter=rInner;
  });

  // Unity core
  const cg=tx.createRadialGradient(cx,cy,0,cx,cy,minR*0.9);
  const ca=S.spiralFlash>0?'ff':'55';
  cg.addColorStop(0,'#f87171'+ca); cg.addColorStop(1,'#f8717100');
  tx.beginPath(); tx.arc(cx,cy,minR*0.9,0,Math.PI*2);
  tx.fillStyle=cg; tx.fill();

  // Tick down pulses / flashes
  for(const k of Object.keys(S.pulses)){
    S.pulses[k].t--;
    if(S.pulses[k].t<=0) delete S.pulses[k];
  }
  for(const d of Object.keys(S.domFlash)){
    S.domFlash[d]--;
    if(S.domFlash[d]<=0) delete S.domFlash[d];
  }
  if(S.spiralFlash>0) S.spiralFlash--;
}

// ── WAVE CANVAS ────────────────────────────────────────────────────────────
function drawWavesOnCanvas(canvas, wsArr) {
  const sec = canvas.parentElement;
  const W = sec.clientWidth, H = sec.clientHeight - 18;
  if (!W || !H || H < 10) return;
  if (canvas.width !== W) canvas.width = W;
  if (canvas.height !== H) canvas.height = H;

  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = '#07070e'; ctx.fillRect(0, 0, W, H);

  const rowH = H / DOM.length;

  DOM.forEach((d, di) => {
    const ws = wsArr[di];
    const baseY = rowH * di + rowH / 2;
    const maxA  = (rowH / 2) * 0.85;

    // Advance carrier phase
    ws.phase += 0.022 * d.freq;

    // Envelope: slow exponential decay toward d.floor (inner rings have higher floor → stay more vivid)
    ws.env = Math.max(d.floor, ws.env * 0.9975);

    // Age spikes — sigma GROWS as spike ages (spreading ripple)
    ws.spikes = ws.spikes.map(s => ({...s, t: s.t - 1})).filter(s => s.t > 0);

    // Row separator
    ctx.beginPath(); ctx.moveTo(0, rowH*(di+1)-.5); ctx.lineTo(W, rowH*(di+1)-.5);
    ctx.strokeStyle = '#1a2234'; ctx.lineWidth = 1; ctx.stroke();

    // Center axis
    ctx.beginPath(); ctx.moveTo(0, baseY); ctx.lineTo(W, baseY);
    ctx.strokeStyle = d.col + '22'; ctx.lineWidth = 1; ctx.stroke();

    // Domain label
    ctx.font = '9px monospace'; ctx.fillStyle = d.col + 'aa';
    ctx.textAlign = 'left'; ctx.textBaseline = 'top';
    ctx.fillText(d.label || d.name.toUpperCase(), 8, rowH * di + 3);

    // Wave path
    ctx.beginPath();
    let first = true;
    for (let x = 0; x < W; x += 1) {
      // Carrier: envelope-scaled sine
      let y = Math.sin(x * 0.013 * d.freq + ws.phase) * ws.env;

      // Spike contributions: Gaussian that SPREADS over time (spreading ripple feel)
      for (const sp of ws.spikes) {
        const age   = 1 - sp.t / sp.maxT;            // 0=fresh, 1=dying
        const sigma = 20 + age * 200;                 // starts tight (20px), spreads to 220px
        const dist  = x - sp.x;
        if (Math.abs(dist) < sigma * 4) {
          const g = Math.exp(-(dist*dist) / (2*sigma*sigma));
          y += sp.a * g * (sp.t / sp.maxT);           // amplitude decays as t→0
        }
      }

      const py = baseY - y * maxA;
      if (first) { ctx.moveTo(x, py); first = false; } else ctx.lineTo(x, py);
    }
    const hasSpikes = ws.spikes.length > 0;
    const envBright = Math.min(1, (ws.env - d.floor) / 0.5);  // how lit-up is this row?
    const alpha = Math.round((0x77 + envBright * 0x88)).toString(16).padStart(2,'0');
    ctx.shadowColor = d.col; ctx.shadowBlur = hasSpikes ? (8 + envBright * 12) : (2 + envBright * 6);
    ctx.strokeStyle = d.col + alpha;
    ctx.lineWidth = hasSpikes ? (1.6 + envBright * 0.8) : (0.9 + envBright * 0.6);
    ctx.stroke();
    ctx.shadowBlur = 0;
  });
}

function drawWaves() {
  drawWavesOnCanvas(document.getElementById('wca'), WS_ADAM);
  drawWavesOnCanvas(document.getElementById('wce'), WS_EVE);
}

// ── EVENT INJECTION ────────────────────────────────────────────────────────
// Compute visual strength from the actual affinity score (natural signal strength from Redis)
// affinity is a float like 18.688 — normalize to 0-1, then scale by event depth type
function computeStrength(evt, di) {
  const aff = parseFloat(evt.affinity || 0);
  // Normalize affinity: typical range 15-35, cap at 1.0
  const affNorm = aff > 0 ? Math.min(0.9, aff / 35) : 0.12;
  // Type multiplier: reflects the semantic depth of the processing event
  const typeScale = evt.type === 'spiral_complete' ? 3.5
    : evt.type === 'domain_complete' ? 2.2
    : evt.type === 'barzakh_flip'    ? 1.6
    : evt.type === 'barzakh_pass'    ? 1.2
    : evt.type === 'layer_done'      ? 1.2
    : evt.type === 'breath'          ? 0.5
    : 0.9;  // layer_step default
  // Inner domains carry more weight per event (Self Awareness beats Body Reflex)
  const depthBonus = di >= 0 ? (di / (DOM.length - 1)) * 0.20 : 0;
  return Math.min(0.95, affNorm * typeScale + depthBonus);
}

function injectEvent(evt){
  // Which wave arrays: adam ring → WS_ADAM, eve/ca → WS_EVE
  const wsArr = (evt.ring === 'adam' || !evt.ring) ? WS_ADAM : WS_EVE;

  // Resolve domain: prefer evt.domain (now properly set by backend), else parse from evt.from
  let domName = (evt.domain || '');
  if (!domName && evt.from && evt.from.includes('_layer')) {
    const p = evt.from.split('_layer');
    domName = p[0].startsWith('p_') ? p[0].slice(2) : p[0];
  }
  const di = DOM.findIndex(d => d.name === domName);

  const strength = computeStrength(evt, di);

  // Envelope boost: all events lift the row's amplitude envelope
  if (di >= 0) {
    const d = DOM[di];
    wsArr[di].env = Math.min(d.floor + 0.65, wsArr[di].env + strength * 0.9);

    // Spatial spike: placed at a random x position so successive spikes spread across canvas
    const canvas = (evt.ring === 'adam' || !evt.ring)
      ? document.getElementById('wca') : document.getElementById('wce');
    const W = (canvas && canvas.width) ? canvas.width : 800;
    const xPos = Math.random() * W;   // random x → spikes spread naturally
    wsArr[di].spikes.push({
      x:    xPos,
      a:    strength * 1.1,
      t:    400,       // 400 frames ≈ 6.5s at 60fps — long tail for continuity
      maxT: 400,
    });
  }

  // Ring-level state updates for the topo diagram
  const ln = parseInt(evt.layer || '0', 10);
  if (di >= 0 && ln > 0) {
    S.pulses[DOM[di].name + ':' + ln] = {affinity: parseFloat(evt.affinity || strength * 20), t: 180, maxT: 180, dir: evt.direction};
  }
  if (evt.type === 'barzakh_flip' || evt.type === 'domain_complete') {
    if (di >= 0) S.domFlash[DOM[di].name] = Math.max(S.domFlash[DOM[di].name]||0, 120);
  }
  if (evt.type === 'spiral_complete') {
    S.spiralFlash = 220;
    WS_ADAM.forEach((ws, i) => { ws.env = Math.min(DOM[i].floor + 0.65, ws.env + 0.25); });
    WS_EVE.forEach((ws, i)  => { ws.env = Math.min(DOM[i].floor + 0.65, ws.env + 0.25); });
  }
}

// ── EVENT LOG ──────────────────────────────────────────────────────────────
const logEl=document.getElementById('log');
let logBuf=[];

function addLog(evt){
  const ts=new Date().toISOString().substr(11,8);
  const from=evt.from||evt.layer||(evt.domain_completed?'domain:'+evt.domain_completed:'');
  const ring=evt.ring?`[${evt.ring}] `:'';
  const dir=evt.direction==='descending'?'↓':evt.direction==='ascending'?'↑':'';
  const pat=evt.pattern?(' '+evt.pattern.substr(0,42)):'';
  logBuf.unshift({ts,type:evt.type,body:`${ring}${from} ${dir}${pat}`});
  if(logBuf.length>60) logBuf.pop();
  logEl.innerHTML=logBuf.map(l=>`<div class="ll"><span class="lts">${l.ts}</span><span class="lt ${l.type}">${l.type}</span><span class="lb">${l.body}</span></div>`).join('');
}

// ── LIVE SSE STREAM (spirit:events + p:spirit:events + ca:spirit:events) ──
function connectStream(){
  const es=new EventSource('/admin/topology/stream');
  es.onmessage=function(e){
    try{
      const evt=JSON.parse(e.data);
      if(evt.type==='heartbeat') return;
      injectEvent(evt);
      // Log all non-breath events; breath would flood the log
      if(evt.type!=='breath') addLog(evt);
    }catch(_){}
  };
  es.onerror=function(){es.close();setTimeout(connectStream,3000);};
}

async function pollStats(){
  try{
    const r=await fetch('/admin/training/status');
    const d=await r.json();
    const job=(d.jobs||[]).find(j=>j.status==='running')||(d.jobs||[])[0];
    if(job){
      document.getElementById('s-prod').textContent=job.total_produced||0;
      document.getElementById('s-cycle').textContent=`${job.current||0}/${job.total_this_cycle||0}`;
      const coh=(job.mean_coherence||0).toFixed(1);
      const lvl=job.coherence_level||'weak';
      const cohEl=document.getElementById('s-coh');
      cohEl.textContent=coh; cohEl.className='sv '+lvl;
      document.getElementById('s-peak').textContent=(job.peak_coherence||0).toFixed(1);
      const lvlEl=document.getElementById('s-lvl');
      lvlEl.textContent=lvl; lvlEl.className='sv '+lvl;
    }
  }catch(e){}
  try{
    const r=await fetch('/admin/coherence');
    const d=await r.json();
    // DEPTH: static total layers across all domains (BARZAKH_THRESHOLD law — never read topology:depth_config)
    const _totalL = DOM.reduce((s,x)=>s+x.layers,0);  // 13+8+5+3+2+1 = 32
    document.getElementById('s-depth').textContent = _totalL + 'L';
    if(d.live){
      const mEl=document.getElementById('s-mode');
      mEl.textContent=d.live.coherence_level||'weak';
      mEl.className='sv '+(d.live.coherence_level||'weak');
    }
  }catch(e){}
}

// ── AUTO-PULSE ─────────────────────────────────────────────────────────────
// Architecture law: inner rings (unity=Self Awareness) are the constant "I Am" — always present.
// outer rings (body=Body Reflex) are reactive — most event-driven, least self-generating.
// So: unity pulses every 300ms, body pulses every 5000ms. INVERTED from layer count.
// Each domain floor is also independent (unity=0.72, body=0.28).
DOM.forEach((d, di) => {
  setInterval(() => {
    const canvasA = document.getElementById('wca');
    const canvasE = document.getElementById('wce');
    const W = (canvasA && canvasA.width) ? canvasA.width : 800;
    // Boost: inner domains stronger per self-pulse (they are more intrinsically active)
    const boost = 0.05 + Math.random() * 0.06 + (di * 0.012);
    for (const [wsArr, cv] of [[WS_ADAM, canvasA], [WS_EVE, canvasE]]) {
      wsArr[di].env = Math.min(d.floor + 0.45, wsArr[di].env + boost);
      wsArr[di].spikes.push({
        x:    Math.random() * ((cv && cv.width) ? cv.width : W),
        a:    0.14 + Math.random() * 0.10 + (di * 0.02),
        t:    320, maxT: 320,
      });
    }
  }, d.pulseMs);  // unity=300ms (constant), body=5000ms (reactive)
});

// ── MAIN LOOP ──────────────────────────────────────────────────────────────
let tStats=0;

function loop(ts){
  drawTopo();
  drawWaves();
  if(ts-tStats>9000){tStats=ts;pollStats();}
  requestAnimationFrame(loop);
}

connectStream(); pollStats();
requestAnimationFrame(loop);
</script>
</body>
</html>"""


@router.get("/world", response_class=HTMLResponse, include_in_schema=False)
async def world_viewer():
    return HTMLResponse(content=_VIEWER_HTML)

