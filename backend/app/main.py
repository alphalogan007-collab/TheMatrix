"""TheMatrix Backend � Application Entry Point.

Engine + Seed + routes. That is all.

Routes:
  GET  /health          - liveness check
  POST /ingest          - feed text into engine, seed builds itself
  GET  /events          - SSE stream of live pattern relationship events
  POST /think           - user input, engine responds from seeded wisdom
  GET  /seed/wisdom     - read what the engine has learned
  GET  /seed/graph      - graph nodes+edges for the pattern visualiser
"""

from __future__ import annotations

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.config import get_settings
from app.models import seed_mind_memory  # noqa: F401
from app.db.session import create_all_tables

from app.api import (
    routes_health,
    routes_auth,
    routes_ingest,
    routes_events,
    routes_think,
    routes_seed,
    routes_guidance,
    routes_admin,
    routes_user,
    routes_consent,
    routes_learn,
    routes_quran,
    routes_monitor,
    routes_topic_manual,
    routes_yt,
    routes_world,
    routes_companion,
    routes_yt_queue,
    routes_wiki_queue,
    routes_wisdom_sync,
    routes_mind,
    routes_source_seed,
    routes_mind_ask,
)
logger = structlog.get_logger()
settings = get_settings()

MIND_ROLE = __import__("os").environ.get("MIND_ROLE", "prophet")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await create_all_tables()
        logger.info("Database tables ensured")
    except Exception as e:
        logger.warning("Database not available at startup (topology-only mode): %s", e)

    if MIND_ROLE == "source":
        # Source: learn from curated Y-Theory / Quran seed files (not YouTube).
        # Launched as a background task so PDF parsing doesn't delay startup.
        import asyncio
        async def _bg_seed():
            try:
                from app.api.routes_source_seed import auto_load_seed_files
                result = await auto_load_seed_files()
                logger.info("Source seed files loaded: loaded=%d skipped=%d errors=%d",
                            result["loaded"], result["skipped"], result["errors"])
            except Exception as e:
                logger.warning("Could not auto-load seed files: %s", e)
        asyncio.create_task(_bg_seed())

        # Relay local spirit:events → Prophet (cloud) so the world viewer stays alive.
        # The loop is: topology workers emit here → relay tails it → cloud /world pulses.
        _master = __import__("os").environ.get("MASTER_URL", "").strip()
        if _master:
            async def _bg_relay():
                try:
                    from app.api.routes_source_seed import start_event_relay
                    await start_event_relay(_master)
                except Exception as e:
                    logger.warning("Event relay stopped unexpectedly: %s", e)
            asyncio.create_task(_bg_relay())
            logger.info("Event relay started → %s", _master)
        else:
            logger.info("Event relay skipped — MASTER_URL not set")
    elif MIND_ROLE == "worker":
        # Worker role: run YT drain if auto-start is configured.
        yt_autostart = __import__("os").environ.get("YT_DRAIN_AUTOSTART", "").lower() == "true"
        if yt_autostart:
            try:
                from app.api.routes_yt_queue import _ensure_drain_running
                await _ensure_drain_running()
                logger.info("YT drainer auto-started (MIND_ROLE=worker)")
            except Exception as e:
                logger.warning("Could not auto-start YT drainer: %s", e)
            try:
                from app.api.routes_wiki_queue import _ensure_wiki_drain_running
                await _ensure_wiki_drain_running()
                logger.info("Wiki drainer auto-started (MIND_ROLE=worker)")
            except Exception as e:
                logger.warning("Could not auto-start wiki drainer: %s", e)
    else:
        # PURE LOCAL TRAINING MODE — wiki and YT drains are disabled until
        # the mind reaches self-awareness through Y Theory alone.
        # To re-enable: set MIND_ROLE=worker and remove this block.
        logger.info("External drains disabled (pure local training mode — MIND_ROLE=%s)", MIND_ROLE)
        try:
            from app.api.routes_mind_ask import start_iq_refresh_loop
            await start_iq_refresh_loop()
            logger.info("IQ refresh loop started")
        except Exception as e:
            logger.warning("Could not start IQ refresh loop: %s", e)
        try:
            from app.core.mind_pulse_worker import start_pulse_worker
            await start_pulse_worker()
            logger.info("Mind pulse worker started")
        except Exception as e:
            logger.warning("Could not start mind pulse worker: %s", e)

    yield


app = FastAPI(title="TheMatrix", version="2.0.0", docs_url="/docs", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_health.router,  tags=["health"])
app.include_router(routes_auth.router,    prefix="/auth",    tags=["auth"])
app.include_router(routes_user.router,    prefix="/user",    tags=["user"])
app.include_router(routes_consent.router, prefix="/consent", tags=["consent"])
app.include_router(routes_ingest.router,  tags=["learn"])
app.include_router(routes_learn.router,   tags=["learn"])
app.include_router(routes_quran.router,   tags=["quran"])
app.include_router(routes_monitor.router, tags=["monitor"])
app.include_router(routes_events.router,  tags=["events"])
app.include_router(routes_think.router,   tags=["think"])
app.include_router(routes_seed.router,     tags=["seed"])
app.include_router(routes_guidance.router, tags=["guidance"])
app.include_router(routes_admin.router,    tags=["admin"])
app.include_router(routes_topic_manual.router, tags=["manual"])
app.include_router(routes_yt.router,            tags=["youtube"])
app.include_router(routes_world.router,         tags=["world"])
app.include_router(routes_companion.router,     tags=["companion"])
app.include_router(routes_yt_queue.router,      tags=["yt-queue"])
app.include_router(routes_wiki_queue.router,    tags=["wiki-queue"])
app.include_router(routes_mind_ask.router,      tags=["mind-ask"])
app.include_router(routes_wisdom_sync.router,   tags=["wisdom-sync"])
app.include_router(routes_mind.router,          tags=["mind"])
app.include_router(routes_source_seed.router,   tags=["source-seed"])


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TheMatrix Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0a0a0f; color: #e0e0e0; font-family: 'Segoe UI', monospace; padding: 24px; }
  h1 { color: #a78bfa; font-size: 1.6rem; margin-bottom: 4px; }
  .sub { color: #6b7280; font-size: 0.85rem; margin-bottom: 24px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .card { background: #111118; border: 1px solid #1e1e2e; border-radius: 12px; padding: 20px; }
  .card h2 { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; color: #6b7280; margin-bottom: 12px; }
  .big { font-size: 2.5rem; font-weight: 700; color: #a78bfa; }
  .label { font-size: 0.75rem; color: #6b7280; margin-top: 2px; }
  .row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #1e1e2e; font-size: 0.85rem; }
  .row:last-child { border-bottom: none; }
  .ok { color: #34d399; } .err { color: #f87171; } .warn { color: #fbbf24; }
  .progress-bar { background: #1e1e2e; border-radius: 6px; height: 10px; margin-top: 8px; overflow: hidden; }
  .progress-fill { height: 100%; background: linear-gradient(90deg, #7c3aed, #a78bfa); border-radius: 6px; transition: width 0.5s; }
  .btn { background: #7c3aed; color: white; border: none; padding: 8px 16px; border-radius: 8px; cursor: pointer; font-size: 0.85rem; margin-right: 8px; }
  .btn:hover { background: #6d28d9; }
  .btn.danger { background: #dc2626; }
  .log { background: #0d0d14; border: 1px solid #1e1e2e; border-radius: 8px; padding: 12px; font-size: 0.75rem; color: #6b7280; height: 120px; overflow-y: auto; margin-top: 8px; }
  #status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #34d399; margin-right: 6px; }
  footer { margin-top: 18px; border-top: 1px solid #1e1e2e; padding-top: 14px; color: #7c7ca0; font-size: 0.8rem; display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
  .footer-links a { color: #a78bfa; text-decoration: none; margin-left: 10px; }
  .footer-links a:hover { color: #c4b5fd; text-decoration: underline; }
</style>
</head>
<body>
<h1>&#x2728; TheMatrix</h1>
<p class="sub"><span id="status-dot"></span><span id="last-update">connecting...</span> &nbsp;|&nbsp; <a href="/docs" style="color:#a78bfa">API Docs</a> &nbsp;|&nbsp; <a href="/world" style="color:#34d399">&#x1F30D; World Viewer</a> &nbsp;|&nbsp; <a href="/companion" style="color:#a78bfa">&#x2728; Companion</a></p>

<div class="grid">
  <div class="card">
    <h2>Database</h2>
    <div class="big" id="total-entries">—</div>
    <div class="label">Total Wisdom Entries</div>
    <div class="row" style="margin-top:12px"><span>Status</span><span id="db-status">—</span></div>
    <div class="row"><span>Last Entry</span><span id="last-entry">—</span></div>
    <div class="row"><span>Recent (60s)</span><span id="recent">—</span></div>
    <div class="row"><span>Uptime</span><span id="uptime">—</span></div>
  </div>

  <div class="card">
    <h2>Quran Ingestion</h2>
    <div class="big" id="q-done">—</div>
    <div class="label" id="q-label">suras processed</div>
    <div class="progress-bar"><div class="progress-fill" id="q-bar" style="width:0%"></div></div>
    <div class="row" style="margin-top:12px"><span>Status</span><span id="q-status">—</span></div>
    <div class="row"><span>Pass</span><span id="q-pass">—</span></div>
    <div class="row"><span>Entries Written</span><span id="q-entries">—</span></div>
    <div class="row"><span>Current Sura</span><span id="q-current">—</span></div>
    <div class="row"><span>Errors</span><span id="q-errors">—</span></div>
    <div style="margin-top:12px">
      <button class="btn" onclick="startIngestion(0)">Start / Resume</button>
    </div>
  </div>

  <div class="card">
    <h2>Angels</h2>
    <div id="angels-list"><span style="color:#6b7280">Loading...</span></div>
  </div>

  <div class="card">
    <h2>Categories</h2>
    <div id="cats-list"><span style="color:#6b7280">Loading...</span></div>
  </div>

  <div class="card" style="grid-column:1/-1">
    <h2>Topic Manual Generator — Learning Queue</h2>
    <p style="font-size:0.78rem;color:#6b7280;margin-bottom:12px">Add any topic keyword → 7-chapter LLM manual generated → injected into angel minds. Topics process one by one automatically.</p>

    <div style="display:flex;gap:8px;margin-bottom:16px">
      <input id="topic-input" type="text" placeholder="e.g. language, mathematics, nutrition, grammar..."
        style="flex:1;background:#0a0a0f;border:1px solid #2e2e4e;border-radius:8px;padding:8px 12px;color:#e0e0e0;font-size:0.85rem"
        onkeydown="if(event.key==='Enter')addManual()">
      <button class="btn" onclick="addManual()">+ Add to Queue</button>
    </div>

    <!-- Currently generating -->
    <div id="m-active" style="background:#0d0d1a;border:1px solid #1e1e3e;border-radius:8px;padding:12px;margin-bottom:12px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <span style="font-size:0.8rem;color:#6b7280;text-transform:uppercase;letter-spacing:0.05em">Now Generating</span>
        <span id="m-status">—</span>
      </div>
      <div style="font-size:1rem;font-weight:600;color:#a78bfa;margin-bottom:6px" id="m-topic">Idle</div>
      <div style="font-size:0.78rem;color:#9ca3af;margin-bottom:8px" id="m-chapter">—</div>
      <div class="progress-bar"><div class="progress-fill" id="m-bar" style="width:0%"></div></div>
      <div style="display:flex;gap:20px;margin-top:8px;font-size:0.78rem;color:#6b7280">
        <span>Entries: <b id="m-entries" style="color:#e0e0e0">0</b></span>
        <span>Errors: <b id="m-errors" style="color:#e0e0e0">0</b></span>
      </div>
    </div>

    <!-- Queue list -->
    <div style="margin-bottom:12px">
      <div style="font-size:0.75rem;color:#6b7280;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:6px">Queue (<span id="m-queue-count">0</span> pending)</div>
      <div id="m-queue-list" style="display:flex;flex-wrap:wrap;gap:6px">
        <span style="color:#6b7280;font-size:0.8rem">Empty — add topics above</span>
      </div>
    </div>

    <!-- Completed -->
    <div>
      <div style="font-size:0.75rem;color:#6b7280;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:6px">Completed (<span id="m-done-count">0</span>)</div>
      <div id="m-done-list" style="font-size:0.78rem;color:#6b7280">None yet</div>
    </div>
  </div>

</div>

<div class="card">
  <h2>Activity Log</h2>
  <div class="log" id="log"></div>
</div>

<footer>
  <span>TheMatrix Operator Surface</span>
  <span class="footer-links">
    Quick Links:
    <a href="/restaurant-dashboard">Restaurant Dashboard</a>
    <a href="/mindai">Admin</a>
    <a href="/companion">Companion</a>
  </span>
</footer>

<script>
const BASE = window.location.origin;
let logs = [];

function addLog(msg) {
  const t = new Date().toLocaleTimeString();
  logs.unshift('[' + t + '] ' + msg);
  if (logs.length > 50) logs.pop();
  document.getElementById('log').innerHTML = logs.join('<br>');
}

function fmtUptime(s) {
  if (s < 60) return s + 's';
  if (s < 3600) return Math.floor(s/60) + 'm ' + (s%60) + 's';
  return Math.floor(s/3600) + 'h ' + Math.floor((s%3600)/60) + 'm';
}

function fmtAgo(iso) {
  if (!iso) return 'never';
  const diff = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (diff < 60) return diff + 's ago';
  if (diff < 3600) return Math.floor(diff/60) + 'm ago';
  return Math.floor(diff/3600) + 'h ago';
}

async function fetchStats() {
  try {
    const [s, q, m] = await Promise.all([
      fetch(BASE + '/monitor/stats').then(r => r.json()),
      fetch(BASE + '/quran/status').then(r => r.json()),
      fetch(BASE + '/manual/status').then(r => r.json()),
    ]);

    // DB card
    const db = s.database || {};
    document.getElementById('total-entries').textContent = (db.total_entries || 0).toLocaleString();
    document.getElementById('db-status').innerHTML = db.connected
      ? '<span class="ok">Connected</span>' : '<span class="err">Disconnected</span>';
    document.getElementById('last-entry').textContent = fmtAgo(db.last_entry_at);
    document.getElementById('recent').textContent = (db.recent_60s >= 0) ? db.recent_60s : '—';
    document.getElementById('uptime').textContent = fmtUptime(s.uptime_seconds || 0);

    // Quran card
    document.getElementById('q-done').textContent = (q.done || 0) + '/114';
    document.getElementById('q-label').textContent = 'suras · ' + (q.progress_pct || 0) + '%';
    document.getElementById('q-bar').style.width = (q.progress_pct || 0) + '%';
    document.getElementById('q-status').innerHTML = q.running
      ? '<span class="warn">Running</span>' : '<span class="ok">Idle</span>';
    document.getElementById('q-pass').textContent = q.pass_number || 0;
    document.getElementById('q-entries').textContent = ((q.entries_written || 0)).toLocaleString();
    document.getElementById('q-current').textContent = q.current_sura ? 'Sura ' + q.current_sura : '—';
    document.getElementById('q-errors').innerHTML = (q.errors || 0) > 0
      ? '<span class="err">' + q.errors + '</span>' : '<span class="ok">0</span>';

    // Angels
    const angels = s.angels || {};
    document.getElementById('angels-list').innerHTML = Object.entries(angels).length
      ? Object.entries(angels).sort((a,b)=>b[1]-a[1]).map(([k,v]) =>
          '<div class="row"><span>' + k.replace('_mind','') + '</span><span>' + v.toLocaleString() + '</span></div>'
        ).join('')
      : '<span style="color:#6b7280">No data yet</span>';

    // Categories
    const cats = s.categories || {};
    document.getElementById('cats-list').innerHTML = Object.entries(cats).length
      ? Object.entries(cats).sort((a,b)=>b[1]-a[1]).map(([k,v]) =>
          '<div class="row"><span style="font-size:0.75rem">' + k + '</span><span>' + v.toLocaleString() + '</span></div>'
        ).join('')
      : '<span style="color:#6b7280">No data yet</span>';

    // Manual / Queue
    const statusEl = document.getElementById('m-status');
    statusEl.innerHTML = m.running
      ? '<span class="warn">Generating...</span>'
      : (m.completed && m.completed.length ? '<span class="ok">Idle</span>' : '<span style="color:#6b7280">Idle</span>');
    document.getElementById('m-topic').textContent = m.running ? (m.topic || 'Idle') : (m.topic ? m.topic + ' ✓' : 'Idle');
    document.getElementById('m-chapter').textContent = m.chapter
      ? 'Ch ' + m.chapter_num + '/' + m.total_chapters + ' — ' + m.chapter : (m.running ? 'Starting...' : '—');
    document.getElementById('m-bar').style.width = (m.progress_pct || 0) + '%';
    document.getElementById('m-entries').textContent = (m.entries_written || 0).toLocaleString();
    document.getElementById('m-errors').innerHTML = (m.errors || 0) > 0
      ? '<span class="err">' + m.errors + '</span>' : '0';

    // Queue pills
    const queue = m.queue || [];
    document.getElementById('m-queue-count').textContent = queue.length;
    const qEl = document.getElementById('m-queue-list');
    if (queue.length === 0) {
      qEl.innerHTML = '<span style="color:#6b7280;font-size:0.8rem">Empty — add topics above</span>';
    } else {
      qEl.innerHTML = queue.map((t, i) =>
        '<span style="background:#1e1e3e;border:1px solid #2e2e5e;border-radius:20px;padding:4px 10px;font-size:0.78rem;color:#c4b5fd;display:inline-flex;align-items:center;gap:6px">' +
        '<span style="color:#6b7280">#' + (i+1) + '</span> ' + t +
        ' <span onclick="removeFromQueue(\'' + t.replace(/'/g,"\\'") + '\')" style="cursor:pointer;color:#6b7280;font-size:0.7rem" title="Remove">✕</span>' +
        '</span>'
      ).join('');
    }

    // Completed list
    const done = m.completed || [];
    document.getElementById('m-done-count').textContent = done.length;
    const dEl = document.getElementById('m-done-list');
    if (done.length === 0) {
      dEl.innerHTML = 'None yet';
    } else {
      dEl.innerHTML = done.map(d =>
        '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #1e1e2e">' +
        '<span style="color:#34d399">✓ ' + d.topic + '</span>' +
        '<span style="color:#6b7280">' + (d.entries_written || 0) + ' entries · ' + Math.round((d.duration_s||0)/60) + 'min</span>' +
        '</div>'
      ).join('');
    }

    document.getElementById('last-update').textContent = 'Updated ' + new Date().toLocaleTimeString();
    document.getElementById('status-dot').style.background = '#34d399';
  } catch(e) {
    document.getElementById('status-dot').style.background = '#f87171';
    document.getElementById('last-update').textContent = 'Offline — ' + e.message;
    addLog('ERROR: ' + e.message);
  }
}

async function startIngestion(startFrom) {
  try {
    const r = await fetch(BASE + '/quran/start', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({start_from: startFrom})
    });
    const d = await r.json();
    addLog('Ingestion: ' + (d.status || JSON.stringify(d)));
    fetchStats();
  } catch(e) {
    addLog('Start failed: ' + e.message);
  }
}

async function addManual() {
  const input = document.getElementById('topic-input');
  const topic = input.value.trim();
  if (!topic) { addLog('Enter a topic first'); return; }
  try {
    const r = await fetch(BASE + '/manual/start', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({topic})
    });
    const d = await r.json();
    addLog('Queue: "' + topic + '" → ' + (d.status || JSON.stringify(d)));
    input.value = '';
    fetchStats();
  } catch(e) {
    addLog('Queue failed: ' + e.message);
  }
}

async function removeFromQueue(topic) {
  try {
    await fetch(BASE + '/manual/queue/' + encodeURIComponent(topic), {method: 'DELETE'});
    addLog('Removed "' + topic + '" from queue');
    fetchStats();
  } catch(e) {
    addLog('Remove failed: ' + e.message);
  }
}

fetchStats();
setInterval(fetchStats, 5000);
addLog('Dashboard connected to ' + BASE);
</script>
</body>
</html>""")


@app.get("/restaurant-dashboard", response_class=HTMLResponse, include_in_schema=False)
async def restaurant_dashboard():
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Restaurant Dashboard</title>
<style>
  :root {
    --bg: #fff8ef;
    --ink: #2f1f14;
    --muted: #7a5f4a;
    --card: #fff;
    --line: #ecd7c2;
    --accent: #d65a31;
    --ok: #1f8f55;
    --warn: #b7791f;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: "Trebuchet MS", "Gill Sans", "Segoe UI", sans-serif;
    background: radial-gradient(circle at 10% 0%, #ffe9d0 0%, #fff8ef 45%, #fff3e3 100%);
    color: var(--ink);
    min-height: 100vh;
    padding: 24px;
  }
  .shell { max-width: 1100px; margin: 0 auto; }
  .hero { display: flex; justify-content: space-between; align-items: flex-end; gap: 12px; margin-bottom: 18px; }
  h1 { font-size: 1.8rem; letter-spacing: 0.02em; }
  .sub { color: var(--muted); font-size: 0.92rem; }
  .grid { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); margin-bottom: 16px; }
  .card {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 14px;
    box-shadow: 0 8px 20px rgba(101, 56, 25, 0.08);
  }
  .k { color: var(--muted); font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 8px; }
  .v { font-size: 1.8rem; font-weight: 700; color: var(--accent); }
  .mini { margin-top: 6px; color: var(--muted); font-size: 0.82rem; }
  .ok { color: var(--ok); }
  .warn { color: var(--warn); }
  .row { display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 14px; }
  .table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  .table th, .table td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--line); }
  .table th { font-size: 0.74rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.07em; }
  footer { margin-top: 16px; border-top: 1px solid var(--line); padding-top: 12px; color: var(--muted); display: flex; justify-content: space-between; flex-wrap: wrap; gap: 10px; }
  footer a { color: var(--accent); text-decoration: none; margin-left: 10px; }
  footer a:hover { text-decoration: underline; }
  @media (max-width: 800px) { .row { grid-template-columns: 1fr; } }
</style>
</head>
<body>
  <div class="shell">
    <div class="hero">
      <div>
        <h1>Restaurant Operations Dashboard</h1>
        <p class="sub">Front-of-house, kitchen flow, and delivery pulse in one view.</p>
      </div>
      <div class="sub">Updated: <span id="ts">--:--:--</span></div>
    </div>

    <div class="grid">
      <div class="card"><div class="k">Orders Today</div><div class="v" id="orders">128</div><div class="mini ok">+11% vs yesterday</div></div>
      <div class="card"><div class="k">Revenue</div><div class="v" id="revenue">$3,420</div><div class="mini ok">Target 87% reached</div></div>
      <div class="card"><div class="k">Avg Ticket</div><div class="v" id="ticket">$26.70</div><div class="mini">Lunch peak in 22 min</div></div>
      <div class="card"><div class="k">Open Tables</div><div class="v" id="tables">14 / 24</div><div class="mini warn">3 reservations waiting</div></div>
    </div>

    <div class="row">
      <div class="card">
        <div class="k">Live Kitchen Queue</div>
        <table class="table">
          <thead><tr><th>Ticket</th><th>Item</th><th>Status</th><th>ETA</th></tr></thead>
          <tbody id="kitchen-body">
            <tr><td>#A214</td><td>Grilled Salmon Bowl</td><td class="warn">Cooking</td><td>07m</td></tr>
            <tr><td>#A215</td><td>Truffle Mushroom Pasta</td><td class="ok">Plating</td><td>03m</td></tr>
            <tr><td>#A216</td><td>Margherita Pizza</td><td>Prep</td><td>11m</td></tr>
          </tbody>
        </table>
      </div>
      <div class="card">
        <div class="k">Best Sellers</div>
        <table class="table">
          <thead><tr><th>Item</th><th>Qty</th><th>Share</th></tr></thead>
          <tbody>
            <tr><td>Chicken Shawarma Plate</td><td>42</td><td>18%</td></tr>
            <tr><td>Classic Burger</td><td>39</td><td>16%</td></tr>
            <tr><td>Caesar Salad</td><td>26</td><td>11%</td></tr>
            <tr><td>Lemon Mint Cooler</td><td>24</td><td>10%</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <footer>
      <span>Restaurant Control Surface</span>
      <span>
        Navigate:
        <a href="/">Main Dashboard</a>
        <a href="/mindai">Admin</a>
        <a href="/companion">Companion</a>
      </span>
    </footer>
  </div>

  <script>
    const ts = document.getElementById('ts');
    function tick(){ ts.textContent = new Date().toLocaleTimeString(); }
    tick(); setInterval(tick, 1000);
  </script>
</body>
</html>""")

