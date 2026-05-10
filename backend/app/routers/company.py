"""
Company of Minds router — CEO dashboard, team health, system health matrix.
Routes extracted from main.py for independent deployment.
"""

from __future__ import annotations

import asyncio
import datetime

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

from app.db.session import AsyncSessionDep

router = APIRouter(tags=["company"])


# ── Company Status ─────────────────────────────────────────────────────────

@router.get("/api/company/status", include_in_schema=False)
async def company_status(db: AsyncSessionDep):
    from app.core.company_report_service import company_health_summary, get_last_reports, collect_all_reports
    last = get_last_reports()
    if not last:
        reports = await collect_all_reports(db)
        await db.commit()
    else:
        reports = last
    summary = company_health_summary()
    summary["teams"] = {
        name: {"health": r.get("health", "UNKNOWN"),
               "risks": len(r.get("risks", [])),
               "proposals": len(r.get("proposals", [])),
               "completed": len(r.get("completed", []))}
        for name, r in reports.items()
    }
    return summary


# ── Run Reports ────────────────────────────────────────────────────────────

@router.post("/api/company/run-reports", include_in_schema=False)
async def run_company_reports(db: AsyncSessionDep):
    from app.core.company_report_service import collect_all_reports
    reports = await collect_all_reports(db)
    await db.commit()
    at_risk = sum(1 for r in reports.values() if r.get("health") == "AT_RISK")
    return {"minds_reported": len(reports), "at_risk": at_risk,
            "healthy": len(reports) - at_risk}


# ── CEO Dashboard ──────────────────────────────────────────────────────────

@router.get("/mind/company", include_in_schema=False)
async def company_dashboard(db: AsyncSessionDep):
    from app.core.company_report_service import collect_all_reports, company_health_summary
    from app.core.seed_mind_store import get_own_entries
    from app.core.seed_mind_memory import INDUCTION

    reports = await collect_all_reports(db)
    await db.commit()
    summary = company_health_summary()

    ceo_reports = await get_own_entries(db, mind_name="grand_planner_mind",
                                        category=INDUCTION, limit=20)
    ceo_lines_parts = []
    for e in ceo_reports[:15]:
        cls = "risk" if "AT_RISK" in (e.tags or "") else "ok"
        ts  = str(e.created_at)[:16] if e.created_at else ""
        ceo_lines_parts.append(
            f"<div class='entry {cls}'>"
            f"<span class='ts'>{ts}</span> "
            f"<span class='title'>{e.title[:100]}</span></div>"
        )
    ceo_lines = "".join(ceo_lines_parts)

    team_rows = ""
    for name, r in sorted(reports.items()):
        health = r.get("health", "UNKNOWN")
        risks_n = len(r.get("risks", []))
        props_n = len(r.get("proposals", []))
        done_n  = len(r.get("completed", []))
        color   = "#ff4444" if health == "AT_RISK" else "#4dc854"
        team_rows += (
            f"<tr><td>{name}</td>"
            f"<td style='color:{color}'>{health}</td>"
            f"<td>{risks_n}</td><td>{props_n}</td><td>{done_n}</td></tr>"
        )

    status_color = "#ff4444" if summary.get("status") == "AT_RISK" else "#4dc854"
    html = f"""<!DOCTYPE html><html><head>
<title>MindAI — CEO Dashboard</title>
<meta charset="utf-8">
<style>
body{{background:#0a0a0a;color:#d0d0d0;font-family:monospace;padding:24px;margin:0}}
h1{{color:#ffd700;font-size:1.4em;margin-bottom:4px}}
h2{{color:#90c8ff;font-size:1em;margin:20px 0 8px}}
.badge{{display:inline-block;padding:4px 14px;border-radius:20px;font-size:0.9em;font-weight:bold;margin:4px}}
table{{border-collapse:collapse;width:100%;margin-bottom:16px}}
th{{background:#1a1a2e;color:#90c8ff;padding:6px 12px;text-align:left}}
td{{padding:5px 12px;border-bottom:1px solid #222}}
tr:hover{{background:#111}}
.entry{{padding:4px 0;border-bottom:1px solid #1a1a1a;font-size:0.85em}}
.ts{{color:#606080;margin-right:8px}}
.title{{color:#c0c0e0}}
.risk .title{{color:#ff8888}}
.btn{{background:#1a1a3a;color:#90c8ff;border:1px solid #304080;padding:8px 20px;
      border-radius:6px;cursor:pointer;font-family:monospace;font-size:0.9em;margin-right:8px}}
.btn:hover{{background:#304080}}
.stat{{display:inline-block;background:#111;border:1px solid #333;border-radius:8px;
       padding:10px 20px;margin:4px;text-align:center}}
.stat-n{{font-size:1.8em;font-weight:bold;color:#ffd700}}
.stat-l{{font-size:0.75em;color:#808080;margin-top:2px}}
</style></head><body>
<h1>MindAI — CEO Intelligence Dashboard</h1>
<p style="color:#606080;font-size:0.8em">grand_planner_mind receives reports from all wings &amp; teams</p>

<div>
  <span class="stat"><div class="stat-n" style="color:{status_color}">{summary.get("status","?")}</div><div class="stat-l">COMPANY STATUS</div></span>
  <span class="stat"><div class="stat-n">{summary.get("minds_online",0)}</div><div class="stat-l">MINDS ONLINE</div></span>
  <span class="stat"><div class="stat-n" style="color:#ff8888">{summary.get("at_risk",0)}</div><div class="stat-l">AT RISK</div></span>
  <span class="stat"><div class="stat-n" style="color:#4dc854">{summary.get("healthy",0)}</div><div class="stat-l">HEALTHY</div></span>
</div>

<div style="margin:16px 0">
  <button class="btn" onclick="runReports()">RUN REPORTS NOW</button>
  <button class="btn" onclick="location.reload()">REFRESH</button>
</div>

<h2>Team & Wing Status</h2>
<table>
<tr><th>Mind</th><th>Health</th><th>Risks</th><th>Proposals</th><th>Completed</th></tr>
{team_rows or "<tr><td colspan='5' style='color:#606080'>No team data yet — click RUN REPORTS NOW</td></tr>"}
</table>

<h2>Recent CEO Reports (from all minds)</h2>
<div style="max-height:400px;overflow-y:auto;background:#0d0d0d;padding:10px;border-radius:8px">
{ceo_lines or "<span style='color:#606080'>No reports yet — reports arrive every 30 minutes or click RUN REPORTS NOW</span>"}
</div>

<script>
async function runReports(){{
  const btn=document.querySelector('.btn');
  btn.textContent='COLLECTING...';
  try{{
    const r=await fetch('/api/company/run-reports',{{method:'POST',credentials:'include'}});
    const d=await r.json();
    btn.textContent='✓ '+d.minds_reported+' minds reported, '+d.at_risk+' at risk';
    setTimeout(()=>location.reload(),2000);
  }}catch(e){{btn.textContent='ERROR: '+e.message;}}
}}
setTimeout(()=>location.reload(),60000);
</script>
</body></html>"""
    return HTMLResponse(html)


# ── System Health Matrix ────────────────────────────────────────────────────

@router.get("/api/system/health-matrix", include_in_schema=False)
async def system_health_matrix(db: AsyncSessionDep):
    import urllib.request as _ur

    def _ping(path: str) -> dict:
        try:
            r = _ur.urlopen(f"http://localhost:8000{path}", timeout=3)
            return {"ok": True, "status": r.getcode()}
        except Exception as e:
            return {"ok": False, "error": str(e)[:60]}

    loop = asyncio.get_event_loop()
    ping_paths = {
        "api.health":         "/health",
        "cell.state":         "/api/mind/cell-state?mind=companion_app_mind",
        "proposals.api":      "/api/mind/proposals",
        "social_fork.trends": "/social-fork/trends",
    }
    endpoint_results = await asyncio.gather(
        *[loop.run_in_executor(None, _ping, p) for p in ping_paths.values()],
        return_exceptions=True
    )
    endpoints = {
        name: (r if isinstance(r, dict) else {"ok": False, "error": str(r)[:60]})
        for name, r in zip(ping_paths.keys(), endpoint_results)
    }

    try:
        from app.core.seed_mind_store import get_own_entries
        from app.core.seed_mind_memory import MISSION_PURPOSE
        r = await get_own_entries(db, mind_name="companion_app_mind", category=MISSION_PURPOSE, limit=1)
        endpoints["db.read"] = {"ok": True, "entries": len(r)}
    except Exception as e:
        endpoints["db.read"] = {"ok": False, "error": str(e)[:60]}

    from sqlalchemy import select, func
    from app.models.seed_mind_memory import SeedMindMemoryEntry
    try:
        total_q = await db.execute(
            select(func.count(SeedMindMemoryEntry.id))
            .where(SeedMindMemoryEntry.is_current == True)
        )
        total = total_q.scalar_one()
        minds_q = await db.execute(
            select(SeedMindMemoryEntry.mind_name, func.count(SeedMindMemoryEntry.id))
            .where(SeedMindMemoryEntry.is_current == True)
            .group_by(SeedMindMemoryEntry.mind_name)
        )
        mind_counts = {row[0]: row[1] for row in minds_q.all()}
    except Exception as e:
        total = 0
        mind_counts = {"error": str(e)[:60]}

    all_ok = all(v.get("ok", False) for v in endpoints.values())
    return {
        "status": "HEALTHY" if all_ok else "DEGRADED",
        "ts": datetime.datetime.utcnow().isoformat(),
        "endpoints": endpoints,
        "total_memory_entries": total,
        "minds": mind_counts,
    }
