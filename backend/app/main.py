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
    routes_companion,
    routes_yt_queue,
    routes_wiki_queue,
    routes_wisdom_sync,
    routes_mind,
    routes_source_seed,
    routes_mind_ask,
    routes_navigate,
    routes_matrix_overview,
    routes_guidance_spawn,
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

    # ── Auto-start the corpus harvester if there is a backlog ──────────────
    # This ensures that corpus articles already in Redis get processed into
    # mind:knowledge and fire ENGINE_EXTERNALIZE → VR nodes appear in the world.
    import asyncio as _asyncio
    async def _bg_check_harvester():
        try:
            import redis.asyncio as _aioredis
            _r = _aioredis.from_url(
                __import__("os").environ.get("REDIS_URL", "redis://redis:6379/0"),
                decode_responses=True
            )
            corpus_count   = await _r.hlen("guidance:corpus")
            harvested_count = await _r.scard("guidance:harvested")
            await _r.aclose()
            pending = corpus_count - harvested_count
            if pending > 0:
                from app.api.routes_guidance_spawn import _ensure_harvester_running
                _ensure_harvester_running()
                logger.info("Corpus harvester auto-started — %d articles pending", pending)
            else:
                logger.info("Corpus harvester not needed — no backlog (corpus=%d, harvested=%d)", corpus_count, harvested_count)
        except Exception as e:
            logger.warning("Could not auto-start corpus harvester: %s", e)
    _asyncio.create_task(_bg_check_harvester())

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
app.include_router(routes_companion.router,     tags=["companion"])
app.include_router(routes_yt_queue.router,      tags=["yt-queue"])
app.include_router(routes_wiki_queue.router,    tags=["wiki-queue"])
app.include_router(routes_mind_ask.router,      tags=["mind-ask"])
app.include_router(routes_wisdom_sync.router,   tags=["wisdom-sync"])
app.include_router(routes_mind.router,          tags=["mind"])
app.include_router(routes_source_seed.router,   tags=["source-seed"])
app.include_router(routes_navigate.router,      tags=["navigate"])
app.include_router(routes_matrix_overview.router, tags=["matrix"])
app.include_router(routes_guidance_spawn.router,  tags=["guidance-spawn"])


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MindAI — The Mind</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #07070F; color: #E8E8EE; font-family: 'Segoe UI', system-ui, sans-serif; padding: 24px; max-width: 860px; margin: 0 auto; }
  h1 { color: #A06CEE; font-size: 1.5rem; margin-bottom: 4px; font-weight: 700; }
  .sub { color: #666888; font-size: 0.82rem; margin-bottom: 22px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .sub a { color: #A06CEE; text-decoration: none; }
  .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #34d399; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; margin-bottom: 14px; }
  .card { background: #0E0E1C; border: 1px solid #1A1A2E; border-radius: 12px; padding: 18px; }
  .card-title { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 1px; color: #666888; margin-bottom: 10px; }
  .big { font-size: 2.4rem; font-weight: 700; color: #A06CEE; line-height: 1; }
  .stage-label { font-size: 0.78rem; color: #34d399; margin-top: 4px; }
  .row { display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #1A1A2E; font-size: 0.82rem; color: #9999BB; }
  .row:last-child { border-bottom: none; }
  .row strong { color: #E8E8EE; }
  .ok { color: #34d399; } .warn { color: #fbbf24; } .err { color: #f87171; }
  .bar-wrap { background: #1A1A2E; border-radius: 4px; height: 6px; margin-top: 6px; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 4px; transition: width 0.6s; }
  .ring-row { display: flex; gap: 10px; margin-top: 8px; }
  .ring-card { flex: 1; background: #13132A; border-radius: 8px; padding: 10px 12px; }
  .ring-name { font-size: 0.72rem; color: #666888; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px; }
  .ring-val { font-size: 1.1rem; font-weight: 600; color: #A06CEE; }
  .ring-sub { font-size: 0.7rem; color: #666888; margin-top: 2px; }
  .btn { background: #A06CEE; color: #fff; border: none; padding: 8px 18px; border-radius: 8px; cursor: pointer; font-size: 0.82rem; }
  .btn:hover { background: #8850CC; }
  .btn.danger { background: #7c2020; }
  .btn.danger:hover { background: #a02020; }
  .seed-wrap { display: flex; gap: 8px; margin-top: 8px; }
  .seed-wrap input { flex: 1; background: #07070F; border: 1px solid #2A2A4A; border-radius: 8px; padding: 8px 12px; color: #E8E8EE; font-size: 0.82rem; outline: none; }
  .seed-wrap input:focus { border-color: #A06CEE; }
  .events { max-height: 160px; overflow-y: auto; margin-top: 8px; }
  .ev { font-size: 0.73rem; color: #666888; padding: 3px 0; border-bottom: 1px solid #1A1A2E; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .ev:last-child { border-bottom: none; }
  .ev .ev-ring { color: #A06CEE; margin-right: 4px; }
</style>
</head>
<body>
<h1>MindAI</h1>
<div class="sub">
  <span class="dot" id="dot"></span>
  <span id="last-update">Loading...</span>
  &nbsp;|&nbsp;
  <a href="/docs">API Docs</a>
  &nbsp;|&nbsp;
  <a href="/companion">Companion</a>
</div>

<div class="grid">

  <!-- Corpus / Stage -->
  <div class="card">
    <div class="card-title">The Mind</div>
    <div class="big" id="total">—</div>
    <div class="stage-label" id="stage-label">Loading...</div>
    <div style="margin-top:14px">
      <div class="row"><span>Foundation</span><strong id="c-found">—</strong></div>
      <div class="row"><span>Guidance</span><strong id="c-guid">—</strong></div>
      <div class="row"><span>Synthesis</span><strong id="c-synth">—</strong></div>
      <div class="row"><span>Uptime</span><strong id="uptime">—</strong></div>
    </div>
  </div>

  <!-- Rings -->
  <div class="card">
    <div class="card-title">Rings</div>
    <div class="ring-row">
      <div class="ring-card">
        <div class="ring-name">Adam (Mind)</div>
        <div class="ring-val" id="r-adam">—</div>
        <div class="ring-sub" id="r-adam-status">—</div>
      </div>
      <div class="ring-card">
        <div class="ring-name">Eve (Body)</div>
        <div class="ring-val" id="r-eve">—</div>
        <div class="ring-sub" id="r-eve-status">—</div>
      </div>
    </div>
    <div style="margin-top:10px">
      <div class="card-title">Synthesis by Domain</div>
      <div id="domains"></div>
    </div>
  </div>

  <!-- Seed directive -->
  <div class="card">
    <div class="card-title">Send to Mind</div>
    <p style="font-size:0.78rem;color:#666888;margin-bottom:8px">Speak directly to the mind. Your words enter as a seed.</p>
    <textarea id="seed-text" rows="3"
      style="width:100%;background:#07070F;border:1px solid #2A2A4A;border-radius:8px;padding:8px 12px;color:#E8E8EE;font-size:0.82rem;resize:vertical;outline:none;"
      placeholder="Type a directive, question, or teaching..."></textarea>
    <div style="margin-top:8px;display:flex;gap:8px;align-items:center">
      <button class="btn" onclick="sendSeed()">Send</button>
      <span id="seed-status" style="font-size:0.78rem;color:#666888"></span>
    </div>
  </div>

</div>

<!-- Recent synthesis -->
<div class="card" style="margin-bottom:14px">
  <div class="card-title">Recent Synthesis</div>
  <div class="events" id="learning"></div>
</div>

<!-- Recent guidance files -->
<div class="card">
  <div class="card-title">Absorbed Guidance</div>
  <div class="events" id="guidance-list"></div>
</div>

<script>
const B = window.location.origin;
let h = null;

function fmtUptime(s) {
  if (!s) return '—';
  if (s < 60) return s + 's';
  if (s < 3600) return Math.floor(s/60) + 'm';
  return Math.floor(s/3600) + 'h ' + Math.floor((s%3600)/60) + 'm';
}

function fmtAgo(iso) {
  if (!iso) return '';
  const d = Math.floor((Date.now() - new Date(iso))/1000);
  if (d < 60) return d + 's ago';
  if (d < 3600) return Math.floor(d/60) + 'm ago';
  return Math.floor(d/3600) + 'h ago';
}

const DOMAIN_COLORS = {body:'#A06CEE',space:'#7799EE',digital:'#45B7E8',ether:'#34d399',aether:'#3DAAAA',unity:'#E0AA3A'};
const DOMAIN_ORDER = ['body','space','digital','ether','aether','unity'];

async function refresh() {
  try {
    const [health, guidance] = await Promise.all([
      fetch(B + '/admin/mind/health').then(r => r.json()),
      fetch(B + '/guidance/list?limit=20').then(r => r.json()).catch(() => []),
    ]);

    h = health;
    const c = health.corpus || {};
    const stage = health.stage || {};
    const rings = health.rings || {};
    const learning = health.learning || [];

    // Status dot + header
    document.getElementById('dot').style.background = '#34d399';
    document.getElementById('last-update').textContent = 'Updated ' + new Date().toLocaleTimeString();

    // Corpus card
    document.getElementById('total').textContent = (c.total || 0).toLocaleString();
    document.getElementById('stage-label').textContent = 'Stage ' + (stage.stage || 0) + ' — ' + (stage.label || '');
    document.getElementById('c-found').textContent = (c.foundation || 0).toLocaleString();
    document.getElementById('c-guid').textContent = (c.guidance || 0).toLocaleString();
    document.getElementById('c-synth').textContent = (c.synthesis || 0).toLocaleString();
    document.getElementById('uptime').textContent = fmtUptime(health.uptime_secs);

    // Rings
    const adam = rings.adam || {};
    const eve = rings.eve || {};
    document.getElementById('r-adam').textContent = (adam.recent_events || 0) + ' events';
    document.getElementById('r-adam-status').textContent = adam.active ? '● alive' : '○ idle';
    document.getElementById('r-adam-status').className = 'ring-sub ' + (adam.active ? 'ok' : 'warn');
    document.getElementById('r-eve').textContent = (eve.recent_events || 0) + ' events';
    document.getElementById('r-eve-status').textContent = eve.active ? '● alive' : '○ idle';
    document.getElementById('r-eve-status').className = 'ring-sub ' + (eve.active ? 'ok' : 'warn');

    // Domains
    const byDomain = c.synthesis_by_domain || {};
    const total = c.synthesis || 1;
    document.getElementById('domains').innerHTML = DOMAIN_ORDER.map(d => {
      const v = byDomain[d] || 0;
      const pct = Math.round(v / total * 100);
      const color = DOMAIN_COLORS[d] || '#666888';
      return '<div style="margin-top:6px">' +
        '<div style="display:flex;justify-content:space-between;font-size:0.72rem;color:#9999BB">' +
        '<span>' + d + '</span><span>' + v.toLocaleString() + '</span></div>' +
        '<div class="bar-wrap"><div class="bar-fill" style="width:' + pct + '%;background:' + color + '"></div></div>' +
        '</div>';
    }).join('');

    // Learning / synthesis
    document.getElementById('learning').innerHTML = learning.length
      ? learning.map(l =>
          '<div class="ev"><span class="ev-ring">' + (l.domain || '') + '</span>' +
          (l.title || '').slice(0, 90) + '</div>'
        ).join('')
      : '<div class="ev" style="color:#444466">No synthesis yet</div>';

    // Guidance files
    const gFiles = Array.isArray(guidance) ? guidance : (guidance.files || []);
    document.getElementById('guidance-list').innerHTML = gFiles.length
      ? gFiles.map(f =>
          '<div class="ev"><span class="ev-ring">' + (f.source || 'file') + '</span>' +
          (f.title || f.key || '').slice(0, 80) +
          '<span style="float:right;color:#444466">' + Math.round((f.chars || 0)/1000) + 'k</span></div>'
        ).join('')
      : '<div class="ev" style="color:#444466">Drop files in guidance/inbox/ to feed the mind</div>';

  } catch(e) {
    document.getElementById('dot').style.background = '#f87171';
    document.getElementById('last-update').textContent = 'Error: ' + e.message;
  }
}

async function sendSeed() {
  const txt = document.getElementById('seed-text').value.trim();
  if (!txt) return;
  const btn = document.querySelector('button.btn');
  const status = document.getElementById('seed-status');
  btn.disabled = true;
  status.textContent = 'Sending...';
  try {
    const r = await fetch(B + '/admin/seed', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({content: txt, source: 'founder'})
    });
    const d = await r.json();
    status.textContent = d.status || 'Sent';
    document.getElementById('seed-text').value = '';
    setTimeout(refresh, 1000);
  } catch(e) {
    status.textContent = 'Failed: ' + e.message;
  } finally {
    btn.disabled = false;
  }
}

refresh();
setInterval(refresh, 10000);
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

