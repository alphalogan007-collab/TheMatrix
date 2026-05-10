"""
oscillation.py -- per-identity oscillation state.

The Pair Law:
    Every identity is an inside/outside pair with oscillation across the boundary.
    Identity = inner field + outer interface + oscillation between them.

Inside / Outside
----------------
  inner_pressure : how much the identity is "full" -- internal activity, unresolved
                   thoughts, contradiction pressure, unsurfaced memories.
                   High inner_pressure drives emission -- the mind radiates outward.

  outer_pressure : how much external input is pressing on the boundary.
                   High outer_pressure drives reception -- the boundary is disturbed.

  boundary_flux  : |inner_pressure - outer_pressure| -- the imbalance that drives the
                   oscillation loop. When flux is high the mind is in active exchange.
                   When flux approaches 0 the mind is in equilibrium (rest/sleep).

Phase Dynamics
--------------
  phase              : θ ∈ [0, 2π) -- current position in the oscillation cycle.
                       Advances by natural_frequency each tick.
  natural_frequency  : ω₀ ∈ (0, 1) -- identity's intrinsic rhythm.
                       Initialised from mean wave field frequency.
  pulse_amplitude    : A(t) -- how strongly the identity is currently oscillating.
                       Tracks mean decayed amplitude of active wave patterns.
  entrainment_strength: how strongly the identity has locked onto global synchrony
                       (from GlobalCouplerState). High entrainment = phase locked.

Emission / Reception
--------------------
  emission_strength  : how much influence the identity is radiating outward.
                       = pulse_amplitude * inner_pressure
  reception_strength : how permeable the boundary is to incoming patterns.
                       = 1 - entrainment_strength * 0.5
                       (highly entrained identity is less easily disturbed)

The oscillation loop per tick:
    1. advance phase by natural_frequency (+ entrainment correction)
    2. compute inner_pressure from unresolved thoughts + contradiction + residual
    3. compute outer_pressure from incoming input urgency + novelty
    4. boundary_flux = |inner_pressure - outer_pressure|
    5. pulse_amplitude tracks mean wave amplitude (EMA)
    6. emission and reception strengths are derived
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List


TWO_PI = 2.0 * math.pi


@dataclass
class OscillationState:
    """Per-identity oscillation state -- the inside/outside pair with a loop."""

    # Phase dynamics
    phase: float = 0.0              # θ ∈ [0, 2π)
    natural_frequency: float = 0.10 # ω₀  ticks^-1  (one cycle per ~63 ticks)
    pulse_amplitude: float = 0.50   # A(t)  mean active wave amplitude

    # Inside / outside boundary
    inner_pressure: float = 0.50    # internal activity / unsurfaced content
    outer_pressure: float = 0.50    # external input pressure
    boundary_flux: float = 0.0      # |inner - outer|  drives exchange

    # Derived coupling
    entrainment_strength: float = 0.0  # 0..1  lock onto GlobalCoupler synchrony
    emission_strength: float = 0.0     # pulse_amplitude * inner_pressure
    reception_strength: float = 1.0    # permeability of boundary

    # History
    last_tick: int = 0
    total_cycles: float = 0.0          # accumulated phase / 2π


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def oscillation_state_to_dict(s: OscillationState) -> dict:
    return {
        "phase":               s.phase,
        "natural_frequency":   s.natural_frequency,
        "pulse_amplitude":     s.pulse_amplitude,
        "inner_pressure":      s.inner_pressure,
        "outer_pressure":      s.outer_pressure,
        "boundary_flux":       s.boundary_flux,
        "entrainment_strength": s.entrainment_strength,
        "emission_strength":   s.emission_strength,
        "reception_strength":  s.reception_strength,
        "last_tick":           s.last_tick,
        "total_cycles":        s.total_cycles,
    }


def oscillation_state_from_dict(d: dict) -> OscillationState:
    return OscillationState(
        phase=float(d.get("phase", 0.0)),
        natural_frequency=float(d.get("natural_frequency", 0.10)),
        pulse_amplitude=float(d.get("pulse_amplitude", 0.50)),
        inner_pressure=float(d.get("inner_pressure", 0.50)),
        outer_pressure=float(d.get("outer_pressure", 0.50)),
        boundary_flux=float(d.get("boundary_flux", 0.0)),
        entrainment_strength=float(d.get("entrainment_strength", 0.0)),
        emission_strength=float(d.get("emission_strength", 0.0)),
        reception_strength=float(d.get("reception_strength", 1.0)),
        last_tick=int(d.get("last_tick", 0)),
        total_cycles=float(d.get("total_cycles", 0.0)),
    )
