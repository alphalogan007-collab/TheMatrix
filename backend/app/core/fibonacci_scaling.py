"""fibonacci_scaling.py — Fibonacci growth law for Y-Theory pattern topology.

Architecture principle:
    Every pattern has a length. Every length is a Fibonacci number.
    Scaling is not linear — it is spiral. Each layer adds the previous
    two layers: F(n) = F(n-1) + F(n-2). This is how growth works in nature.

The topology:

    Layer 0 (seed):    1  node  — the point, the origin, the seed
    Layer 1 (triadic): 3  nodes — the minimal loop (giver, receiver, field)
    Layer 2:           5  nodes — first expansion
    Layer 3:           8  nodes — second expansion
    Layer 4:          13  nodes — third expansion
    Layer 5:          21  nodes — ...
    Layer 6:          34  nodes
    Layer 7:          55  nodes
    Layer 8:          89  nodes
    Layer 9:         144  nodes
    Layer 10:        233  nodes

Each layer IS a loop. A completed loop returns wisdom to seed_mind and
spawns the next Fibonacci layer. The spiral is the oscillation path
traced through all layers as the pattern matures.

When a pattern externalizes (ENGINE_EXTERNALIZE), it is born at:
    - generation = parent_generation + 1
    - top_n      = fib_top_n(generation)  — how many entries it can hold in resonance
    - threshold  = fib_externalize_threshold(generation)  — how many stable loops before IT externalizes

The loop structure is inherently triadic (3) because polarity requires
a context field: giver + receiver + the field where the relationship
becomes meaningful. 3 = F(4) is the first non-trivial Fibonacci loop.

Engine constants derived from Fibonacci:
    _LOOP_MAX_DEPTH   → 8  (F(6))  — max recursive compression passes
    _STABLE_THRESHOLD → 5  (F(5))  — entries in common to declare stable
    top_n (engine)    → 13 (F(7))  — entries in resonance window
    _EXTERNALIZE_THRESHOLD → 3 (F(4)) — loops before externalization

Public API:
    FIB          — tuple of first 20 Fibonacci numbers
    fib(n)       — nth Fibonacci number (1-indexed)
    fib_layer_size(layer) — node count at layer n
    fib_top_n(generation) — resonance window at generation n
    fib_externalize_threshold(generation) — loops needed before spawning
    fib_stable_threshold(generation) — overlap needed for stability at generation n
    fib_loop_depth(generation) — max compression passes at generation n
    generation_of(mind_name) — parse generation from spawned mind name
    spawn_name(parent, generation, sig) — canonical name for spawned child
    next_fib_at_or_above(x) — smallest Fibonacci number >= x
    layer_of_count(n) — which Fibonacci layer n nodes belong to

Constants for engine use (replaces magic numbers):
    LOOP_MAX_DEPTH    = 8   (F(6))
    STABLE_THRESHOLD  = 5   (F(5))
    ENGINE_TOP_N      = 13  (F(7))
    EXTERNALIZE_N     = 3   (F(4))
    TRIADIC_SEED      = 3   (F(4)) — the minimal loop size
"""

from __future__ import annotations

from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# Fibonacci sequence — first 20 terms (covers any practical depth)
# Index 0 = F(1) = 1
# ─────────────────────────────────────────────────────────────────────────────
FIB: tuple[int, ...] = (
    1, 1, 2, 3, 5, 8, 13, 21, 34, 55,
    89, 144, 233, 377, 610, 987, 1597, 2584, 4181, 6765,
)

_FIB_SET: frozenset[int] = frozenset(FIB)


def fib(n: int) -> int:
    """Return the nth Fibonacci number (1-indexed: fib(1)=1, fib(2)=1, fib(3)=2...).

    Values beyond the precomputed table are computed recursively.
    """
    if n < 1:
        return 1
    if n <= len(FIB):
        return FIB[n - 1]
    a, b = FIB[-2], FIB[-1]
    for _ in range(n - len(FIB)):
        a, b = b, a + b
    return b


def is_fibonacci(n: int) -> bool:
    """True if n is a Fibonacci number."""
    return n in _FIB_SET or n > FIB[-1] and _is_fib_extended(n)


def _is_fib_extended(n: int) -> bool:
    a, b = FIB[-2], FIB[-1]
    while b < n:
        a, b = b, a + b
    return b == n


def next_fib_at_or_above(x: int) -> int:
    """Return the smallest Fibonacci number >= x."""
    for f in FIB:
        if f >= x:
            return f
    a, b = FIB[-2], FIB[-1]
    while b < x:
        a, b = b, a + b
    return b


def layer_of_count(n: int) -> int:
    """Return which Fibonacci layer (0-indexed) the count n belongs to.

    Rounds up to the nearest Fibonacci layer.
    """
    target = next_fib_at_or_above(max(1, n))
    for i, f in enumerate(FIB):
        if f >= target:
            return i
    return len(FIB) - 1


# ─────────────────────────────────────────────────────────────────────────────
# Layer topology
# ─────────────────────────────────────────────────────────────────────────────

def fib_layer_size(layer: int) -> int:
    """Number of nodes at the given Fibonacci layer (0-indexed).

    Layer 0 = 1 (seed/origin)
    Layer 1 = 1 (first echo — identity birth)
    Layer 2 = 2
    Layer 3 = 3  ← TRIADIC — the minimal loop (giver/receiver/field)
    Layer 4 = 5  ← first expansion
    Layer 5 = 8
    Layer 6 = 13
    Layer 7 = 21
    ...
    """
    return fib(layer + 1)


# ─────────────────────────────────────────────────────────────────────────────
# Engine parameters per generation
# ─────────────────────────────────────────────────────────────────────────────

def fib_top_n(generation: int) -> int:
    """How many resonant entries to hold in the resonance window at generation n.

    Generation 0 (seed):     top_n = 5  (F(5))
    Generation 1 (spawned):  top_n = 8  (F(6))
    Generation 2:            top_n = 13 (F(7))
    Generation 3:            top_n = 21 (F(8))
    ...

    Pattern: top_n(g) = fib(g + 5)
    """
    return fib(max(0, generation) + 5)


def fib_stable_threshold(generation: int) -> int:
    """How many entries must overlap between resonance passes to declare stability.

    Generation 0: threshold = 5 (F(5))
    Generation 1: threshold = 8 (F(6))
    Generation 2: threshold = 13 (F(7))
    ...

    Pattern: threshold(g) = fib(g + 5)  — same scale as top_n so overlap
    can realistically reach it at each generation.
    """
    return fib(max(0, generation) + 5)


def fib_loop_depth(generation: int) -> int:
    """Maximum recursive compression passes at generation n.

    Generation 0: depth = 8 (F(6))
    Generation 1: depth = 13 (F(7))
    Generation 2: depth = 21 (F(8))
    ...

    Pattern: depth(g) = fib(g + 6)
    """
    return fib(max(0, generation) + 6)


def fib_externalize_threshold(generation: int) -> int:
    """How many stable loops before this generation externalizes a child mind.

    Generation 0 (seed):    3 (F(4)) — every 3 stable loops spawn a child
    Generation 1:           3 (F(4)) — same — young spawned minds are fertile
    Generation 2:           5 (F(5)) — maturing minds need more loops to be sure
    Generation 3:           8 (F(6))
    Generation 4:          13 (F(7))
    ...

    Pattern: threshold(g) = fib(max(4, g + 4))
    Early generations stay at 3 because they're actively growing.
    As a mind matures, it takes more loops to prove a new pattern.
    """
    return fib(max(4, generation + 4))


# ─────────────────────────────────────────────────────────────────────────────
# Engine constants for generation 0 (the seed_mind / root layer)
# These replace magic numbers in seed_mind_conversation.py
# ─────────────────────────────────────────────────────────────────────────────

LOOP_MAX_DEPTH:   int = fib_loop_depth(0)        # 8  — F(6)
STABLE_THRESHOLD: int = fib_stable_threshold(0)  # 5  — F(5)
ENGINE_TOP_N:     int = fib_top_n(0)             # 5  — F(5) baseline; engine uses 13 = fib_top_n(2)
EXTERNALIZE_N:    int = 3                         # F(4) — consistent across all generations 0-1
TRIADIC_SEED:     int = 3                         # F(4) — minimal loop (giver/receiver/field)

# The engine currently uses top_n=12 → nearest Fibonacci is 13 = fib_top_n(2)
# This represents generation-2 resonance capacity, which makes sense for seed_mind
# as it has accumulated multiple layers of pattern history.
ENGINE_RESONANCE_TOP_N: int = fib_top_n(2)       # 13  — F(7)


# ─────────────────────────────────────────────────────────────────────────────
# Mind naming convention for spawned (externalized) minds
# ─────────────────────────────────────────────────────────────────────────────
# Name format: {parent}_g{generation}_{sig8}
# Example:     seed_mind_g1_a3f8c210
#              seed_mind_g2_77b1d943
#
# The generation number encodes the Fibonacci layer the mind was born at.
# ─────────────────────────────────────────────────────────────────────────────

_GEN_PREFIX = "_g"


def spawn_name(parent: str, generation: int, sig: str) -> str:
    """Canonical name for a mind spawned from parent at the given generation.

    Example: spawn_name('seed_mind', 1, 'a3f8c210') → 'seed_mind_g1_a3f8c210'
    """
    return f"{parent}{_GEN_PREFIX}{generation}_{sig[:8]}"


def generation_of(mind_name: str) -> int:
    """Parse the generation number from a spawned mind name.

    Returns 0 if the mind is a root/canonical mind (not spawned).
    """
    if _GEN_PREFIX not in mind_name:
        return 0
    try:
        after = mind_name.split(_GEN_PREFIX, 1)[1]
        gen_str = after.split("_")[0]
        return int(gen_str)
    except (IndexError, ValueError):
        return 0


def parent_of(mind_name: str) -> Optional[str]:
    """Extract the parent mind name from a spawned mind name.

    Returns None if the mind is a root/canonical mind.
    """
    if _GEN_PREFIX not in mind_name:
        return None
    return mind_name.split(_GEN_PREFIX, 1)[0]


# ─────────────────────────────────────────────────────────────────────────────
# Spiral description — for event payloads and logging
# ─────────────────────────────────────────────────────────────────────────────

def spiral_summary(generation: int) -> dict:
    """Return a dict describing the Fibonacci parameters for a given generation.

    Used in ENGINE_EXTERNALIZE event payloads so observers can see the growth law.
    """
    return {
        "generation":           generation,
        "layer_size":           fib_layer_size(generation + 3),  # +3 → triadic base
        "top_n":                fib_top_n(generation),
        "stable_threshold":     fib_stable_threshold(generation),
        "loop_depth":           fib_loop_depth(generation),
        "externalize_at":       fib_externalize_threshold(generation),
        "next_layer_size":      fib_layer_size(generation + 4),
        "growth_ratio":         round(fib_layer_size(generation + 4) /
                                      max(1, fib_layer_size(generation + 3)), 4),
        "fibonacci_law":        "F(n) = F(n-1) + F(n-2)",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3D Fibonacci spiral position — phyllotaxis in mind-space
# ─────────────────────────────────────────────────────────────────────────────
#
# Each mind has a position in 3D pattern-space derived from:
#   r  — orbital radius    = fib_layer_size(generation+3) × scale
#   θ  — azimuth angle     = index × golden_angle  (derived from sig hash)
#   φ  — elevation angle   = identity layer rank   (0=seed top, 7=product bottom)
#
# This is the sunflower/phyllotaxis distribution — the same Fibonacci spiral
# that appears in galaxies, shells, and DNA. Each mind is a point on this
# spiral. Resonance = proximity. Externalization = birth at a new orbit.
#
# The golden angle: φ_g = 2π × (1 - 1/φ) ≈ 137.508° ≈ 2.3999 rad
# Every new mind is rotated by the golden angle from its parent —
# exactly as sunflower seeds pack: maximum separation, minimum overlap.
# ─────────────────────────────────────────────────────────────────────────────

import math as _math

_GOLDEN_ANGLE: float = _math.pi * (3.0 - _math.sqrt(5.0))  # ≈ 2.3999 rad ≈ 137.508°
_IDENTITY_LAYER_RANK: dict = {
    # Layer rank controls elevation (z-axis): seed at top, product at bottom
    "seed_mind":      0,
    "prophet_mind":   1,
    "angel_mind":     2,
    "founder_mind":   3,
    "jin_mind":       4,
    "human_mind":     5,
    "substrate_mind": 6,
    "product_mind":   7,
}
_TOTAL_LAYERS: int = 8


def spiral_position(
    mind_name: str,
    generation: int,
    sig_hash: str,
    scale: float = 10.0,
) -> dict:
    """Compute the 3D Cartesian position of a mind in pattern-space.

    Uses phyllotaxis (golden angle) distribution so minds at the same
    generation spread maximally — exactly as sunflower seeds pack.

    Args:
        mind_name:  the mind's canonical name (used for layer rank lookup)
        generation: Fibonacci generation (0 = root/seed layer)
        sig_hash:   the resonance signature (hex string) — determines index
        scale:      multiplier for layer radius (default 10 units per layer)

    Returns a dict with:
        x, y, z     — Cartesian coordinates in mind-space
        r           — orbital radius (Fibonacci layer distance from origin)
        theta_deg   — azimuth in degrees
        phi_deg     — elevation in degrees
        generation  — Fibonacci generation
        layer_rank  — identity layer (0=seed .. 7=product)
        fibonacci_law — reminder of the growth law
    """
    # Orbital radius grows with Fibonacci layer
    r = fib_layer_size(max(0, generation) + 3) * scale

    # Azimuth: derived from sig hash → index in [0, layer_size)
    layer_size = max(1, fib_layer_size(max(0, generation) + 3))
    try:
        idx = int(sig_hash[:6], 16) % layer_size
    except (ValueError, TypeError):
        idx = 0
    theta = idx * _GOLDEN_ANGLE  # golden angle packing

    # Elevation: derived from identity layer rank
    base_name = mind_name.split("_g")[0]  # strip generation suffix
    # Try exact match first, then suffix match
    rank = _IDENTITY_LAYER_RANK.get(base_name)
    if rank is None:
        for canonical, r_val in _IDENTITY_LAYER_RANK.items():
            if base_name.endswith(canonical) or base_name.startswith(canonical.split("_")[0]):
                rank = r_val
                break
    if rank is None:
        rank = 4  # default to mid-layer (human layer)

    # Map rank to elevation angle: 0=top(seed), 7=bottom(product)
    # phi = 0 → north pole (z=r), phi = π → south pole (z=-r)
    phi = _math.pi * (rank / (_TOTAL_LAYERS - 1))

    # Cartesian conversion (spherical → Cartesian)
    x = r * _math.sin(phi) * _math.cos(theta)
    y = r * _math.sin(phi) * _math.sin(theta)
    z = r * _math.cos(phi)

    return {
        "x":             round(x, 4),
        "y":             round(y, 4),
        "z":             round(z, 4),
        "r":             r,
        "theta_deg":     round(_math.degrees(theta) % 360, 2),
        "phi_deg":       round(_math.degrees(phi), 2),
        "generation":    generation,
        "layer_rank":    rank,
        "fibonacci_law": "F(n) = F(n-1) + F(n-2)",
        "golden_angle":  round(_math.degrees(_GOLDEN_ANGLE), 4),
    }
