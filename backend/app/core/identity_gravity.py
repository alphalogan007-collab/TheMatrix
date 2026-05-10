"""
identity_gravity.py -- Identity Gravity and Pattern Mass.

The Identity Gravity Law:

    G_ij = (M_i * M_j * R_ij * C_ij) / (D_ij + eps) - N_ij

Where:
    G_ij  = attraction between identity field i and incoming pattern j
    M_i   = mass of the identity (belief field / moral root / stable memory)
    M_j   = mass of the incoming pattern
    R_ij  = resonance = cosine similarity of 6D centers
    C_ij  = closure compatibility = how much pattern j supports identity continuity
    D_ij  = distance = 1 - R_ij (semantic / phase mismatch)
    N_ij  = repulsion = contradiction score + moral conflict + noise

Pattern Mass
------------
Mass is not physical weight. It is accumulated identity significance:

    M = amplitude
      + 0.3 * memory_strength  (observation_count normalised)
      + 0.2 * belief_bonus     (1.0 if pattern is a crystallised Belief)
      + 0.2 * moral_bonus      (1.5 if moral_root, 1.2 if stable_truth)
      + 0.1 * closure_bonus    (mean_closure)
      + 0.1 * emotional_charge (absolute value from memory trace if linked)

Gravity Effects
---------------
A positive G_ij means the identity field ATTRACTS the pattern:
  -> ctx.cache.extra["attracted_patterns"] lists (pat_id, G, reason) tuples
  -> wave_memory.reinforce_pattern(pat_id, boost) is called with G * attract_boost

A negative G_ij means the identity field REPELS the pattern:
  -> patterns with strong negative gravity are candidates for quarantine
  -> MoralLayer already blocks harmful content; gravity adds a softer economic
     signal earlier in the cycle

Emission and Reception via Gravity
-----------------------------------
When a Belief or MoralRoot has high mass it radiates outward as an
"interpretation field" -- every new pattern that enters the mind is
evaluated against that field first.  This is the Belief-as-Sun model:
  "A strong belief attracts related patterns into its interpretation field."

The moral root is always the highest-mass attractor:
    moral_root mass bonus = 1.5
    stable_truth bonus    = 1.2
    knowledge             = 1.0
    noise                 = 0.3
    harmful               = 0.1  (low mass -> quarantine rather than attract)
"""

from __future__ import annotations

import math
from typing import Dict, List, NamedTuple, Optional


_EPS = 1e-6

# Per-category mass multipliers
_MASS_CAT: Dict[str, float] = {
    "moral_root":   1.5,
    "stable_truth": 1.2,
    "knowledge":    1.0,
    "noise":        0.3,
    "harmful":      0.1,
}


# ---------------------------------------------------------------------------
# Pattern mass
# ---------------------------------------------------------------------------

def pattern_mass(
    amplitude: float,
    observation_count: int,
    mean_closure: float,
    category: str,
    is_belief: bool = False,
    emotional_charge: float = 0.0,
) -> float:
    """
    Compute the scalar mass of a single wave pattern.

    mass = category_multiplier * (
        amplitude
        + 0.30 * memory_strength
        + 0.20 * belief_bonus
        + 0.10 * closure_bonus
        + 0.10 * |emotional_charge|
    )

    capped at 2.0 to keep gravity finite.
    """
    memory_strength = min(1.0, observation_count / 50.0)
    belief_bonus    = 1.0 if is_belief else 0.0
    cat_mult        = _MASS_CAT.get(category, 1.0)

    raw = (
        amplitude
        + 0.30 * memory_strength
        + 0.20 * belief_bonus
        + 0.10 * mean_closure
        + 0.10 * abs(emotional_charge)
    )
    return min(2.0, cat_mult * raw)


# ---------------------------------------------------------------------------
# Identity (belief field) mass
# ---------------------------------------------------------------------------

def identity_mass(
    belief_amplitudes: List[float],
    moral_amplitude: float,
    mean_closure: float,
) -> float:
    """
    Aggregate mass of the identity's belief/moral field.

    M_identity = moral_amplitude * 1.5
               + mean(belief_amplitudes) * 1.2
               + mean_closure * 0.5

    This is M_i in the gravity formula.
    """
    belief_mean = (sum(belief_amplitudes) / len(belief_amplitudes)
                   if belief_amplitudes else 0.0)
    return min(3.0,
        moral_amplitude * 1.5
        + belief_mean   * 1.2
        + mean_closure  * 0.5
    )


# ---------------------------------------------------------------------------
# Cosine similarity (local copy to avoid circular import)
# ---------------------------------------------------------------------------

def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(y * y for y in b))
    if na < _EPS or nb < _EPS:
        return 0.0
    return max(-1.0, min(1.0, dot / (na * nb)))


# ---------------------------------------------------------------------------
# Gravity score
# ---------------------------------------------------------------------------

class GravityResult(NamedTuple):
    pattern_id: str
    G: float         # positive = attract, negative = repel
    M_j: float       # pattern mass
    resonance: float # cosine similarity to identity centroid
    reason: str      # human-readable note for logs


def gravity_score(
    pattern_id: str,
    pattern_center: List[float],
    pattern_amplitude: float,
    pattern_observation_count: int,
    pattern_mean_closure: float,
    pattern_category: str,
    is_belief: bool,
    identity_centroid: List[float],   # mean belief center (6D)
    M_i: float,                        # identity mass
    contradiction_score: float,        # from BeliefState
    moral_alignment: float,            # from MoralLayer 0..1
    closure_score: float,              # from PipelineCache
    emotional_charge: float = 0.0,
) -> GravityResult:
    """
    Compute the full gravity score for one pattern against the identity field.

    G_ij = (M_i * M_j * R_ij * C_ij) / (D_ij + eps) - N_ij
    """
    M_j = pattern_mass(
        amplitude=pattern_amplitude,
        observation_count=pattern_observation_count,
        mean_closure=pattern_mean_closure,
        category=pattern_category,
        is_belief=is_belief,
        emotional_charge=emotional_charge,
    )

    R_ij = max(0.0, _cosine(pattern_center, identity_centroid))  # resonance [0,1]
    D_ij = 1.0 - R_ij                                           # distance  [0,1]
    C_ij = closure_score                                         # closure compatibility

    # Repulsion: contradiction + moral conflict + category noise
    cat_noise = 1.0 - _MASS_CAT.get(pattern_category, 1.0) / 1.5
    N_ij = (
        contradiction_score * 0.40
        + (1.0 - moral_alignment) * 0.40
        + cat_noise * 0.20
    )

    numerator = M_i * M_j * R_ij * C_ij
    G = numerator / (D_ij + _EPS) - N_ij

    if G > 0.5:
        reason = f"attracted: res={R_ij:.2f} mass={M_j:.2f}"
    elif G < -0.2:
        reason = f"repelled: noise={cat_noise:.2f} moral_misalign={1-moral_alignment:.2f}"
    else:
        reason = f"neutral: G={G:.3f}"

    return GravityResult(
        pattern_id=pattern_id,
        G=G,
        M_j=M_j,
        resonance=R_ij,
        reason=reason,
    )
