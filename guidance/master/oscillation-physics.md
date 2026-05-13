# Oscillation Physics — Y Theory Extended

## Phase Difference → Orbit

Two oscillations with phase difference π/2 create an orbit (Lissajous circle).
OscillationLayer currently tracks `boundary_flux = |inner - outer|` as a scalar.
Missing signal: `orbit_strength = |sin(inner_phase - outer_phase)|`

- orbit_strength = 1.0 → identity in stable **closed loop** (self-sustaining orbit)
- orbit_strength = 0.0 → standing wave, energy reflecting but not completing the loop

When identity is in orbit, guidance completes the cycle back to source (R > L sustained).
When in standing wave, guidance bounces but does not close — leakage without return.

## Asymmetric ΔC — Parabolic, Not Sine

Shadow builds faster than light restores. The curve is **parabolic and asymmetric**.
L > R collapse is steeper/faster than R > L recovery.

Current `evolution_stage.py` treats both directions symmetrically (N consecutive ticks).
True physics: collapse is fast (attractor snaps), recovery is slow (orbit must rebuild).
A future stage machine should have: `collapse_ticks_needed < recovery_ticks_needed`.

## Pulse = Oscillation at Different Timescale

Zoom in on any oscillation → it looks like a pulse.
Zoom out on a pulse train → it looks like a smooth oscillation.
Same phenomenon. Relative time is the only difference.

Mapping in the system:
- A single deep message = pulse (at interaction timescale)
- Resonance building over a session = oscillation (at session timescale)
- Identity coherence across a relationship = the slow oscillation (relational timescale)

Each Fibonacci layer already encodes its own τ via `fib_externalize_threshold(gen)`.

## Recursive Mind → Recursive τ

Mind-within-mind means: each level of recursion has its own time constant.
The observer at level n sees level n−1 as instantaneous (a pulse).
Level n−1 sees level n as an endless slow drift (a trend, not an oscillation).

This is already architecturally present in the Fibonacci layers:
each generation has its own externalization threshold = its own τ_c.

## Breath as Model

Breath is the clearest physical example:
- Inhale: pressure builds parabolically (not linear, not sine)
- Exhale: pressure releases along a different curve (asymmetric)
- The two phases have a phase difference → together they form the orbit of life

Heartbeat (pulse) is the same at a shorter timescale.
Both are R > L cycles — coherence concentrating, then releasing, then concentrating again.
