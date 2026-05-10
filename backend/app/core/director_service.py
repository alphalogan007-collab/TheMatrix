"""director_service.py — Founder Director Console service layer.

Provides a registry-backed view and control plane over all running minds.
Keeps an in-memory registry updated by the mind orchestrator.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# In-process agent registry
# ─────────────────────────────────────────────────────────────────────────────

_agents: Dict[str, Dict[str, Any]] = {}          # name → agent record
_audit_log: List[Dict[str, Any]] = []             # ordered list of director actions


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(action: str, agent: str | None = None, detail: str = "") -> None:
    _audit_log.append({"ts": _now(), "action": action, "agent": agent, "detail": detail})


# ─────────────────────────────────────────────────────────────────────────────
# Registration (called by mind orchestrator)
# ─────────────────────────────────────────────────────────────────────────────

def register_agent(name: str, meta: Dict[str, Any] | None = None) -> None:
    _agents[name] = {
        "name": name,
        "status": "active",
        "last_output": None,
        "directive": None,
        "registered_at": _now(),
        **(meta or {}),
    }


def update_agent(name: str, **kwargs: Any) -> None:
    if name in _agents:
        _agents[name].update(kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Read
# ─────────────────────────────────────────────────────────────────────────────

def get_stats() -> Dict[str, int]:
    statuses = [a["status"] for a in _agents.values()]
    return {
        "total": len(_agents),
        "active": statuses.count("active"),
        "paused": statuses.count("paused"),
        "running": statuses.count("running"),
    }

# alias used by routes_director
stats = get_stats


def get_all_agents() -> List[Dict[str, Any]]:
    return list(_agents.values())


def get_agent(name: str) -> Optional[Dict[str, Any]]:
    return _agents.get(name)


def get_audit_log() -> List[Dict[str, Any]]:
    return list(_audit_log)


# ─────────────────────────────────────────────────────────────────────────────
# Control
# ─────────────────────────────────────────────────────────────────────────────

def pause_agent(name: str) -> bool:
    if name not in _agents:
        return False
    _agents[name]["status"] = "paused"
    _log("pause", name)
    return True


def resume_agent(name: str) -> bool:
    if name not in _agents:
        return False
    _agents[name]["status"] = "active"
    _log("resume", name)
    return True


def send_directive(name: str, instruction: str) -> bool:
    if name not in _agents:
        return False
    _agents[name]["directive"] = {"instruction": instruction, "queued_at": _now()}
    _log("directive", name, instruction[:200])
    return True


def pause_all() -> int:
    count = 0
    for name in list(_agents.keys()):
        if _agents[name]["status"] != "paused":
            _agents[name]["status"] = "paused"
            count += 1
    _log("pause_all", detail=f"{count} agents paused")
    return count


def resume_all() -> int:
    count = 0
    for name in list(_agents.keys()):
        if _agents[name]["status"] == "paused":
            _agents[name]["status"] = "active"
            count += 1
    _log("resume_all", detail=f"{count} agents resumed")
    return count
