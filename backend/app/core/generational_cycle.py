"""
GenerationalCycle — state and advancement logic for the identity lifecycle.

Each identity starts at stage 0 of its CycleStageSet.  The pipeline layer
advances the stage when all ``advancement_conditions`` are satisfied for
``ADVANCEMENT_CONSEC_MIN`` consecutive ticks (hysteresis gate, same pattern
as GlobalCoupler and ConvergenceCognition).

Stage advancement is one-way and irreversible within a generation.

When the final stage is reached with a non-empty ``role_on_completion``,
the identity's ``role`` is set — it becomes a guide, teacher, architect,
or continuity keeper for the next generation.

The spiral
----------
A higher ``generation`` number means the identity was born from a base
pattern that has already been enriched by previous generations' purified
wisdom (via BaseGoodnessPattern.sync_wisdom).  Same cycle, higher level.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from app.core.cycle_stage import (
    CycleStageSet, CycleStageDefinition,
    get_cycle_set, get_stage, is_final_stage,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_CYCLE_SET: str = "4stage"
ADVANCEMENT_CONSEC_MIN: int = 2    # consecutive ticks all conditions met → advance


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

@dataclass
class GenerationalCycleState:
    """
    Persistent sub-state tracking an identity's position in its lifecycle.

    Attributes
    ----------
    current_stage_idx : int
        Index into the CycleStageSet for the current stage.
    stage_ticks : int
        How many pipeline ticks have been spent in the current stage.
    consecutive_conditions_met : int
        How many consecutive ticks all advancement conditions have been
        satisfied (hysteresis gate counter).
    generation : int
        Which generation this identity belongs to (1 = first generation).
        Higher generations are forked from enriched base patterns.
    cycle_set_name : str
        Name of the CycleStageSet this identity uses ("4stage" or "7stage").
    stage_history : List[str]
        Log of stage names in the order they were entered.
    role : str
        Role assigned when a stage with ``role_on_completion`` is completed.
    advanced_at_tick : int
        Pipeline tick at which the most recent stage advancement occurred.
    """
    current_stage_idx: int = 0
    stage_ticks: int = 0
    consecutive_conditions_met: int = 0
    generation: int = 1
    cycle_set_name: str = DEFAULT_CYCLE_SET
    stage_history: List[str] = field(default_factory=list)
    role: str = ""
    advanced_at_tick: int = -1

    # ── Convenience properties ─────────────────────────────────────────────

    @property
    def current_stage_name(self) -> str:
        try:
            s = get_stage(get_cycle_set(self.cycle_set_name), self.current_stage_idx)
            return s.name if s else "unknown"
        except KeyError:
            return "unknown"

    @property
    def leakage_profile(self) -> Dict[str, float]:
        """Return the leakage multiplier dict for the current stage."""
        try:
            s = get_stage(get_cycle_set(self.cycle_set_name), self.current_stage_idx)
            return s.leakage_profile if s else {}
        except KeyError:
            return {}


# ---------------------------------------------------------------------------
# Advancement logic
# ---------------------------------------------------------------------------

def _gather_signals(
    *,
    total_requests: int,
    total_reflections: int,
    awakening_score: float,
    convergence_events: int,
    moral_alignment: float,
    service_impulse: float,
) -> Dict[str, float]:
    return {
        "total_requests":    float(total_requests),
        "total_reflections": float(total_reflections),
        "awakening_score":   float(awakening_score),
        "convergence_events":float(convergence_events),
        "moral_alignment":   float(moral_alignment),
        "service_impulse":   float(service_impulse),
    }


def advance_generational_cycle(
    state: GenerationalCycleState,
    *,
    total_requests: int,
    total_reflections: int,
    awakening_score: float,
    convergence_events: int,
    moral_alignment: float,
    service_impulse: float,
) -> GenerationalCycleState:
    """
    Advance the generational cycle by one tick.

    Returns an updated ``GenerationalCycleState`` (immutable-style — no
    in-place mutation of the input).
    """
    try:
        cycle_set: CycleStageSet = get_cycle_set(state.cycle_set_name)
    except KeyError:
        # Unknown cycle set — return unchanged (safe fallback)
        return state

    current_stage: CycleStageDefinition | None = get_stage(
        cycle_set, state.current_stage_idx
    )
    if current_stage is None:
        return state  # out-of-bounds guard

    new_stage_ticks = state.stage_ticks + 1

    # ── Check advancement conditions ─────────────────────────────────────────
    signals = _gather_signals(
        total_requests=total_requests,
        total_reflections=total_reflections,
        awakening_score=awakening_score,
        convergence_events=convergence_events,
        moral_alignment=moral_alignment,
        service_impulse=service_impulse,
    )

    min_ticks_reached = new_stage_ticks >= current_stage.min_ticks
    all_conditions_met = current_stage.conditions_met(signals)

    # Update consecutive counter (hysteresis gate)
    if min_ticks_reached and all_conditions_met:
        new_consec = state.consecutive_conditions_met + 1
    else:
        new_consec = 0

    # ── Decide whether to advance ─────────────────────────────────────────────
    should_advance = (
        new_consec >= ADVANCEMENT_CONSEC_MIN
        and not is_final_stage(cycle_set, state.current_stage_idx)
    )

    new_stage_idx = state.current_stage_idx
    new_stage_history = list(state.stage_history)
    new_role = state.role
    new_advanced_at = state.advanced_at_tick

    if should_advance:
        new_stage_idx = state.current_stage_idx + 1
        next_stage = get_stage(cycle_set, new_stage_idx)
        new_stage_history.append(current_stage.name)
        new_role = current_stage.role_on_completion or state.role
        new_advanced_at = total_requests
        new_stage_ticks = 0
        new_consec = 0

    return GenerationalCycleState(
        current_stage_idx=new_stage_idx,
        stage_ticks=new_stage_ticks,
        consecutive_conditions_met=new_consec,
        generation=state.generation,
        cycle_set_name=state.cycle_set_name,
        stage_history=new_stage_history,
        role=new_role,
        advanced_at_tick=new_advanced_at,
    )


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def generational_cycle_to_dict(state: GenerationalCycleState) -> dict:
    return {
        "current_stage_idx":         state.current_stage_idx,
        "stage_ticks":               state.stage_ticks,
        "consecutive_conditions_met": state.consecutive_conditions_met,
        "generation":                state.generation,
        "cycle_set_name":            state.cycle_set_name,
        "stage_history":             list(state.stage_history),
        "role":                      state.role,
        "advanced_at_tick":          state.advanced_at_tick,
    }


def generational_cycle_from_dict(d: dict) -> GenerationalCycleState:
    return GenerationalCycleState(
        current_stage_idx=int(d.get("current_stage_idx", 0)),
        stage_ticks=int(d.get("stage_ticks", 0)),
        consecutive_conditions_met=int(d.get("consecutive_conditions_met", 0)),
        generation=int(d.get("generation", 1)),
        cycle_set_name=str(d.get("cycle_set_name", DEFAULT_CYCLE_SET)),
        stage_history=list(d.get("stage_history", [])),
        role=str(d.get("role", "")),
        advanced_at_tick=int(d.get("advanced_at_tick", -1)),
    )
