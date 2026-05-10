"""routes_learn.py — API to trigger and monitor Fibonacci learning cycles."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from app.db.session import AsyncSessionDep

router = APIRouter()

_cycle_state: dict = {"running": False, "steps_done": 0, "last_result": None}


class LearnRequest(BaseModel):
    steps: int = 6   # Fibonacci steps: 6 → covers all 8 phases, 8 → deep revisit


class LearnStatus(BaseModel):
    running:    bool
    steps_done: int
    last_result: Optional[dict]


@router.post("/learn/start")
async def start_learning(req: LearnRequest, db: AsyncSessionDep, bg: BackgroundTasks):
    """Start Fibonacci learning schedule in the background.

    Sequence: F(1)=1, F(2)=1, F(3)=2, F(4)=3, F(5)=5, F(6)=8 ...
    Each step feeds ONE input per active phase. Never completes one area fully.
    """
    if _cycle_state["running"]:
        return {"status": "already_running", "steps_done": _cycle_state["steps_done"]}

    async def _run():
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "learn"))
        from learn.cycle import run_fibonacci
        _cycle_state["running"] = True
        try:
            results = await run_fibonacci(db, total_steps=req.steps)
            _cycle_state["last_result"] = {
                "steps_run":   req.steps,
                "total_entries": sum(r["total_entries"] for r in results),
                "steps":       results,
            }
            _cycle_state["steps_done"] += req.steps
        finally:
            _cycle_state["running"] = False

    bg.add_task(_run)
    fib_seq = []
    a, b = 1, 1
    for _ in range(req.steps):
        fib_seq.append(a)
        a, b = b, a + b
    return {"status": "started", "steps": req.steps, "fibonacci_sequence": fib_seq}


@router.get("/learn/status", response_model=LearnStatus)
async def learn_status():
    return LearnStatus(
        running=_cycle_state["running"],
        steps_done=_cycle_state["steps_done"],
        last_result=_cycle_state["last_result"],
    )


@router.get("/learn/plan")
async def get_plan():
    """Return the Quranic creation-order plan with Fibonacci ratios."""
    def _fib(n: int) -> int:
        a, b = 1, 1
        for _ in range(n - 1):
            a, b = b, a + b
        return a

    PHASES = [
        {"key": "qalam",   "arabic": "القلم",           "english": "The Pen",              "ratio": 0.05, "y_layer": "SeedEnrichmentLayer",  "angel": "kiraman_katibin_mind"},
        {"key": "arsh",    "arabic": "العرش",           "english": "The Throne",            "ratio": 0.08, "y_layer": "GlobalCouplerLayer",    "angel": "throne_mind"},
        {"key": "maa",     "arabic": "الماء",           "english": "The Water",             "ratio": 0.08, "y_layer": "ResidualRealityLayer",  "angel": "raphael_mind"},
        {"key": "samawat", "arabic": "السماوات والأرض", "english": "Heavens & Earth",       "ratio": 0.14, "y_layer": "WorldInputLayer",      "angel": "israfil_mind"},
        {"key": "malaika", "arabic": "الملائكة",        "english": "Angels",                "ratio": 0.18, "y_layer": "WisdomTransferLayer",  "angel": "gabriel_mind"},
        {"key": "hayah",   "arabic": "الحياة",          "english": "Life",                  "ratio": 0.15, "y_layer": "OscillationLayer",     "angel": "michael_mind"},
        {"key": "insan",   "arabic": "الإنسان",         "english": "Human",                 "ratio": 0.18, "y_layer": "ConsciousLayer",       "angel": "guardian_mind"},
        {"key": "aql",     "arabic": "العقل والأخلاق",  "english": "Intellect & Morality",  "ratio": 0.14, "y_layer": "MoralLayer",           "angel": "malik_mind"},
    ]

    fib_seq = [_fib(i + 1) for i in range(8)]
    # first_active_at_step: phase i becomes active at step i+1 in Fibonacci schedule
    return {
        "fibonacci_sequence": fib_seq,
        "phases": [
            {**p, "first_active_at_step": i + 1}
            for i, p in enumerate(PHASES)
        ],
    }
