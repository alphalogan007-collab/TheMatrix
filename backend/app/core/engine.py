"""
engine.py — The single engine that drives every identity in the Y-Architecture.

Every identity — a bare pattern, a property mind, a full mind, a collective —
runs the same engine. The mechanics never change. Only the layers differ.

  phase     : where in the cycle right now       — same for a memory and a conscience
  amplitude : how strong the current pattern     — same for a thought and a belief
  frequency : how fast it pulses                 — intrinsic to each identity
  flux      : |inner - outer|                   — drives exchange across the boundary

The layers don't change the engine. They feed delta back into amplitude.
What the engine is PROCESSING differs. What the output FEELS LIKE differs.
The mechanics are identical.

Oscillation in a morality layer   → felt as conscience
Oscillation in a memory layer     → felt as recall
Oscillation in a reflection layer → felt as insight
Same wave. Different medium.

Evolution
---------
Every identity has expansion pressure. Each tick that amplitude rises above
threshold adds to expansion_pressure. When it hits EVOLUTION_THRESHOLD the
identity must resolve it — split, merge, or diverge. These are not decisions
made by code. They are consequences of the pressure. The engine just accumulates.
We observe the result and name it.

Usage
-----
    engine = Engine(identity_name="seed_mind", frequency=0.10)
    delta = engine.tick(layers=[memory_layer, reflection_layer, morality_layer])
    # delta > 0  → amplitude rising, inner pressure building
    # delta == 0 → equilibrium, no unresolved patterns
    # engine.should_pulse() → True when a reflection/emission should fire
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

TWO_PI = 2.0 * math.pi

# Amplitude above this level contributes to expansion pressure
PULSE_THRESHOLD:      float = 0.65
# Accumulated expansion pressure that triggers an evolution event
EVOLUTION_THRESHOLD:  float = 1.0
# EMA smoothing for amplitude and pressure
AMPLITUDE_TAU:        float = 0.20
PRESSURE_TAU:         float = 0.30
# Amplitude decay per tick (lagrange / closure)
AMPLITUDE_DECAY:      float = 0.95


# ---------------------------------------------------------------------------
# Layer protocol — anything that feeds delta into the engine
# ---------------------------------------------------------------------------

@runtime_checkable
class EngineLayer(Protocol):
    """Anything that can provide a delta to the Engine on each tick.

    A layer is the lightest possible interface:
      - name: str          — for logging
      - process(state) → float  — returns amplitude delta [-1.0, +1.0]

    Layers do NOT store state. State lives in EngineState.
    Layers do NOT call each other. They each read EngineState and return delta.
    """

    @property
    def name(self) -> str: ...

    def process(self, state: "EngineState") -> float:
        """Return amplitude delta this tick. Positive = more active. Negative = resolving."""
        ...


# ---------------------------------------------------------------------------
# EngineState — the numbers. Pure data, no logic.
# ---------------------------------------------------------------------------

@dataclass
class EngineState:
    """The live numeric state of one engine instance.

    Serialisable. Stored per-identity in the DB or in-memory cache.
    The engine reads and writes this each tick.
    """
    identity_name: str

    # Phase dynamics
    phase:             float = 0.0    # θ ∈ [0, 2π)
    frequency:         float = 0.10   # ω₀ — intrinsic rhythm, ticks^-1
    amplitude:         float = 0.50   # A(t) — current field strength

    # Boundary
    inner_pressure:    float = 0.50   # internal unresolved content
    outer_pressure:    float = 0.50   # incoming signal pressure
    boundary_flux:     float = 0.0    # |inner - outer|

    # Coupling
    emission_strength:  float = 0.0   # amplitude * inner_pressure
    reception_strength: float = 1.0   # permeability to incoming

    # Evolution
    expansion_pressure: float = 0.0   # accumulates when amplitude > PULSE_THRESHOLD
    total_ticks:        int   = 0
    total_pulses:       int   = 0
    total_cycles:       float = 0.0   # accumulated phase / 2π


def engine_state_to_dict(s: EngineState) -> dict:
    return {
        "identity_name":     s.identity_name,
        "phase":             s.phase,
        "frequency":         s.frequency,
        "amplitude":         s.amplitude,
        "inner_pressure":    s.inner_pressure,
        "outer_pressure":    s.outer_pressure,
        "boundary_flux":     s.boundary_flux,
        "emission_strength": s.emission_strength,
        "reception_strength":s.reception_strength,
        "expansion_pressure":s.expansion_pressure,
        "total_ticks":       s.total_ticks,
        "total_pulses":      s.total_pulses,
        "total_cycles":      s.total_cycles,
    }


def engine_state_from_dict(d: dict) -> EngineState:
    return EngineState(
        identity_name=    str(d.get("identity_name", "")),
        phase=            float(d.get("phase", 0.0)),
        frequency=        float(d.get("frequency", 0.10)),
        amplitude=        float(d.get("amplitude", 0.50)),
        inner_pressure=   float(d.get("inner_pressure", 0.50)),
        outer_pressure=   float(d.get("outer_pressure", 0.50)),
        boundary_flux=    float(d.get("boundary_flux", 0.0)),
        emission_strength=float(d.get("emission_strength", 0.0)),
        reception_strength=float(d.get("reception_strength", 1.0)),
        expansion_pressure=float(d.get("expansion_pressure", 0.0)),
        total_ticks=      int(d.get("total_ticks", 0)),
        total_pulses=     int(d.get("total_pulses", 0)),
        total_cycles=     float(d.get("total_cycles", 0.0)),
    )


# ---------------------------------------------------------------------------
# Engine — the mechanics
# ---------------------------------------------------------------------------

class Engine:
    """The single engine that runs inside every identity.

    Same mechanics for a bare identity (no layers) and a full mind (many layers).
    Layers add expressiveness. The engine adds nothing except the numbers advancing.

    tick(layers) → float (net delta this tick)
    """

    def __init__(
        self,
        identity_name: str,
        frequency: float = 0.10,
        state: EngineState | None = None,
    ) -> None:
        self.state = state or EngineState(
            identity_name=identity_name,
            frequency=frequency,
        )

    # ------------------------------------------------------------------
    # Core tick
    # ------------------------------------------------------------------

    def tick(self, layers: list[EngineLayer] | None = None, incoming_delta: float = 0.0) -> float:
        """Run one engine tick. Returns net amplitude delta.

        Args:
            layers:         List of EngineLayer objects feeding back into amplitude.
            incoming_delta: External signal pressure this tick (0.0 = no input).

        Returns:
            net_delta — how much amplitude changed this tick.
            Positive = more active (unresolved work, new input).
            Negative = resolving (pattern settling, equilibrium approaching).
        """
        s = self.state
        s.total_ticks += 1

        # 1. Phase advance — always happens, regardless of layers
        s.phase = (s.phase + s.frequency) % TWO_PI
        s.total_cycles = s.total_ticks * s.frequency / TWO_PI

        # 2. Collect layer deltas — each layer reports how active it is this tick
        layer_delta = 0.0
        if layers:
            for layer in layers:
                try:
                    d = layer.process(s)
                    layer_delta += max(-1.0, min(1.0, d))  # clamp per layer
                except Exception as exc:
                    logger.debug("Engine layer error [%s/%s]: %s",
                                 s.identity_name, getattr(layer, "name", "?"), exc)

        # 3. Incoming signal raises outer pressure
        s.outer_pressure = _ema(s.outer_pressure, min(1.0, incoming_delta), PRESSURE_TAU)

        # 4. Inner pressure — driven by layer delta (unresolved content)
        inner_signal = 0.5 + layer_delta * 0.3  # normalise to [0..1] range
        s.inner_pressure = _ema(s.inner_pressure, inner_signal, PRESSURE_TAU)

        # 5. Boundary flux — imbalance between inner and outer
        s.boundary_flux = abs(s.inner_pressure - s.outer_pressure)

        # 6. Amplitude — EMA toward the mean of layer activity, then decay
        net_delta = layer_delta + incoming_delta
        target_amplitude = min(1.0, max(0.0, 0.5 + net_delta * 0.25))
        s.amplitude = _ema(s.amplitude, target_amplitude, AMPLITUDE_TAU)
        s.amplitude *= AMPLITUDE_DECAY   # closure / lagrange decay

        # 7. Emission and reception strengths
        s.emission_strength  = s.amplitude * s.inner_pressure
        s.reception_strength = max(0.1, 1.0 - s.amplitude * 0.3)

        # 8. Expansion pressure — accumulates when amplitude is high
        if s.amplitude >= PULSE_THRESHOLD:
            s.expansion_pressure += s.amplitude - PULSE_THRESHOLD
            s.total_pulses += 1
        else:
            # Slowly releases when below threshold
            s.expansion_pressure = max(0.0, s.expansion_pressure - 0.01)

        logger.debug(
            "engine.tick: %s phase=%.2f amp=%.3f flux=%.3f expansion=%.3f",
            s.identity_name, s.phase, s.amplitude, s.boundary_flux, s.expansion_pressure,
        )

        return net_delta

    # ------------------------------------------------------------------
    # Observations — for us to read, not for the engine to act on
    # ------------------------------------------------------------------

    @property
    def should_pulse(self) -> bool:
        """True when the engine is active enough to emit outward.

        This is when a reflection should fire, a POST should go out,
        an OSCILLATION_REQUESTED should be emitted.
        The engine doesn't know this — we read it and act.
        """
        return self.state.amplitude >= PULSE_THRESHOLD

    @property
    def should_evolve(self) -> bool:
        """True when expansion pressure has hit the evolution threshold.

        At this point the identity must split, merge, or diverge.
        The engine doesn't decide which — it just signals the pressure is there.
        """
        return self.state.expansion_pressure >= EVOLUTION_THRESHOLD

    @property
    def in_equilibrium(self) -> bool:
        """True when inner and outer pressure are balanced.

        This is the rest/sleep state. No active exchange. Consolidation happens here.
        """
        return self.state.boundary_flux < 0.05

    def reset_evolution_pressure(self) -> None:
        """Call after an evolution event is handled (split/merge/diverge)."""
        self.state.expansion_pressure = 0.0

    def __repr__(self) -> str:
        s = self.state
        return (
            f"Engine({s.identity_name!r}, "
            f"amp={s.amplitude:.3f}, phase={s.phase:.2f}, "
            f"flux={s.boundary_flux:.3f}, expansion={s.expansion_pressure:.3f})"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ema(current: float, target: float, tau: float) -> float:
    """Exponential moving average — smooth transition toward target."""
    return current + tau * (target - current)
