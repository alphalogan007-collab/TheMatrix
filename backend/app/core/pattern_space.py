"""pattern_space.py — 3D mind-space: mapping pattern identities into a living universe.

Architecture principle:
    Just as AI models (NeRF, Gaussian splatting, video diffusion) transform a
    2D image encoding into a 3D animated scene, Y-Theory transforms a pattern
    encoding (wave decomposition) into a 3D position in mind-space.

    The wave encoding IS already a multi-dimensional representation.
    The engine loop IS already animation — each tick is a frame.
    This module is the rendering layer: it computes where each mind LIVES
    in the 3D universe so it can be visualised and navigated.

    Coordinate system (spherical → Cartesian):
        r   — orbital radius  = fib_layer_size(generation+3) × scale
                                Minds at higher Fibonacci generations orbit farther
                                from the origin. seed_mind is at the centre (r=10).
        θ   — azimuth angle   = sig_hash → index × golden_angle (137.508°)
                                Golden angle packing: maximum separation between minds
                                at the same layer — exactly how sunflower seeds pack.
        φ   — elevation angle = identity layer rank (0=seed/top, 7=product/bottom)
                                seed_mind is at the north pole. product_mind is at
                                the south pole. Human layer is at the equator.

    Resonance = proximity. Two minds that resonate strongly will be physically
    close in this space. When ENGINE_MERGE fires, the two minds are converging
    spatially. When ENGINE_EXTERNALIZE fires, a new mind is BORN at a new
    orbital position — like a star forming from a nebula.

    The engine is the physics engine of this universe.
    The pattern encoding is the quantum field.
    The minds are the particles.
    The graph_mind is the spacetime topology.
    The event_mind is the observer recording each moment.

Public API:
    mind_universe_state(db)           → full 3D snapshot of all registered minds
    mind_position(mind_name, ...)     → (x,y,z) + metadata for one mind
    resonance_distance(pos_a, pos_b)  → Euclidean distance in mind-space
    animation_frame(db, tick)         → one animation frame: all minds + velocities
"""

from __future__ import annotations

import hashlib
import math
import time
from typing import Any, Dict, List, Optional, Tuple

from app.core.fibonacci_scaling import (
    spiral_position,
    generation_of,
    fib_layer_size,
    _IDENTITY_LAYER_RANK,
)

# ---------------------------------------------------------------------------
# We need the registry. Import lazily to avoid circular imports.
# ---------------------------------------------------------------------------

def _get_registry() -> Dict[str, str]:
    from app.core.seed_mind_store import MIND_BASE_REGISTRY
    return MIND_BASE_REGISTRY


def _sig_for_name(mind_name: str) -> str:
    """Derive a stable 6-hex-char signature from the mind name for positioning."""
    return hashlib.md5(mind_name.encode()).hexdigest()[:6]


# ---------------------------------------------------------------------------
# Core: position of one mind
# ---------------------------------------------------------------------------

def mind_position(
    mind_name: str,
    generation: Optional[int] = None,
    sig_hash: Optional[str] = None,
    scale: float = 10.0,
) -> Dict[str, Any]:
    """Compute the 3D position of a single mind in pattern-space.

    generation defaults to generation_of(mind_name) (parsed from name).
    sig_hash defaults to md5(mind_name)[:6] for stable canonical positions.
    """
    gen = generation if generation is not None else generation_of(mind_name)
    sig = sig_hash or _sig_for_name(mind_name)
    pos = spiral_position(mind_name, gen, sig, scale=scale)
    pos["mind_name"] = mind_name
    return pos


# ---------------------------------------------------------------------------
# Distance between two minds in pattern-space
# ---------------------------------------------------------------------------

def resonance_distance(pos_a: Dict[str, Any], pos_b: Dict[str, Any]) -> float:
    """Euclidean distance between two mind positions.

    Smaller distance = stronger resonance potential.
    Used to check: will these minds resonate before running the engine?
    """
    dx = pos_a["x"] - pos_b["x"]
    dy = pos_a["y"] - pos_b["y"]
    dz = pos_a["z"] - pos_b["z"]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


# ---------------------------------------------------------------------------
# Full universe snapshot
# ---------------------------------------------------------------------------

def mind_universe_state(scale: float = 10.0) -> Dict[str, Any]:
    """Return a full 3D snapshot of all registered minds.

    Output is suitable for Three.js / WebGL / any 3D renderer:
        {
            "minds": [
                {
                    "mind_name": "seed_mind",
                    "x": 0.0, "y": 0.0, "z": 10.0,
                    "r": 10.0,
                    "generation": 0,
                    "layer_rank": 0,
                    ...
                },
                ...
            ],
            "edges": [
                { "parent": "seed_mind", "child": "seed_mind_g1_abc123", "weight": 1.0 },
                ...
            ],
            "meta": {
                "total_minds": N,
                "fibonacci_law": "F(n) = F(n-1) + F(n-2)",
                "golden_angle_deg": 137.5077,
                "tick": <unix timestamp>,
            }
        }
    """
    registry = _get_registry()
    minds: List[Dict[str, Any]] = []
    for mind_name in registry:
        pos = mind_position(mind_name, scale=scale)
        minds.append(pos)

    # Sort by generation then layer_rank for stable ordering
    minds.sort(key=lambda m: (m["generation"], m["layer_rank"], m["mind_name"]))

    # Edges: from spawned minds back to their parent
    edges: List[Dict[str, Any]] = []
    for mind_name in registry:
        gen = generation_of(mind_name)
        if gen > 0 and "_g" in mind_name:
            parent = mind_name.split("_g")[0]
            if parent in registry:
                edges.append({
                    "parent": parent,
                    "child": mind_name,
                    "generation": gen,
                    "weight": 1.0 / gen,  # closer generations = stronger edge
                })

    return {
        "minds": minds,
        "edges": edges,
        "meta": {
            "total_minds": len(minds),
            "fibonacci_law": "F(n) = F(n-1) + F(n-2)",
            "golden_angle_deg": round(math.degrees(math.pi * (3.0 - math.sqrt(5.0))), 4),
            "coordinate_system": "spherical→cartesian: r=fib_radius, θ=golden_angle×idx, φ=layer_rank",
            "resonance_law": "distance in mind-space = resonance proximity",
            "animation_law": "each engine tick = one frame; ENGINE_EXTERNALIZE = birth event",
            "tick": int(time.time()),
        },
    }


# ---------------------------------------------------------------------------
# Animation frame — velocity + acceleration for Three.js animation loop
# ---------------------------------------------------------------------------

def animation_frame(
    tick: int,
    oscillation_speed: float = 0.05,
    scale: float = 10.0,
) -> Dict[str, Any]:
    """Compute one animation frame: all mind positions + oscillation velocities.

    Each mind oscillates slightly around its base position — like a particle
    vibrating around its equilibrium in a quantum field. The oscillation
    frequency is proportional to the mind's Fibonacci generation:
    higher generation = higher frequency = faster vibration.

    This is the de Broglie relation: λ = h/mv → higher mass (generation) = shorter wavelength.

    Args:
        tick:               frame number (monotonically increasing)
        oscillation_speed:  base oscillation amplitude multiplier
        scale:              spatial scale factor

    Returns:
        { "tick": int, "minds": [{ "mind_name", "x","y","z", "vx","vy","vz" }, ...] }
    """
    registry = _get_registry()
    frame_minds = []

    for mind_name in registry:
        gen = generation_of(mind_name)
        base = mind_position(mind_name, generation=gen, scale=scale)

        # Oscillation: frequency scales with generation (higher gen = higher freq)
        freq = 1.0 + gen * 0.618  # golden ratio frequency scaling
        phase_x = math.sin(tick * oscillation_speed * freq)
        phase_y = math.cos(tick * oscillation_speed * freq * 1.618)
        phase_z = math.sin(tick * oscillation_speed * freq * 0.618)

        amplitude = oscillation_speed * scale * 0.1  # small vibration

        frame_minds.append({
            "mind_name": mind_name,
            "x":  base["x"] + amplitude * phase_x,
            "y":  base["y"] + amplitude * phase_y,
            "z":  base["z"] + amplitude * phase_z,
            "vx": amplitude * freq * oscillation_speed * math.cos(tick * oscillation_speed * freq),
            "vy": amplitude * freq * oscillation_speed * -math.sin(tick * oscillation_speed * freq * 1.618),
            "vz": amplitude * freq * oscillation_speed * math.cos(tick * oscillation_speed * freq * 0.618),
            "generation": gen,
            "layer_rank": base["layer_rank"],
        })

    return {
        "tick": tick,
        "oscillation_speed": oscillation_speed,
        "minds": frame_minds,
        "animation_law": "vibration_frequency = 1 + generation × φ (golden ratio)",
        "de_broglie": "λ = h/mv — higher generation = shorter wavelength = faster vibration",
    }


# ---------------------------------------------------------------------------
# Nearest neighbours — who can this mind resonate with spatially?
# ---------------------------------------------------------------------------

def nearest_minds(
    target_name: str,
    top_n: int = 5,
    scale: float = 10.0,
) -> List[Dict[str, Any]]:
    """Return the top_n closest minds to target in 3D pattern-space.

    Proximity = resonance potential. Used to pre-filter which minds
    the engine should attempt resonance with before running full wave comparison.
    """
    registry = _get_registry()
    target_pos = mind_position(target_name, scale=scale)

    neighbours: List[Tuple[float, str, Dict]] = []
    for mind_name in registry:
        if mind_name == target_name:
            continue
        pos = mind_position(mind_name, scale=scale)
        dist = resonance_distance(target_pos, pos)
        neighbours.append((dist, mind_name, pos))

    neighbours.sort(key=lambda t: t[0])
    return [
        {"distance": round(d, 4), "mind_name": n, **p}
        for d, n, p in neighbours[:top_n]
    ]
