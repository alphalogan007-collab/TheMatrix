"""
BasinClassifier — identity basin state classifier.

Adapted from existence_lab BasinTransitionLayer.

Basin states:
  - collapse    : energy < -0.08   → identity destabilising, high risk
  - metastable  : -0.08 ≤ e < 0.08 → uncertain, needs support
  - stable      :  0.08 ≤ e < 0.20 → healthy equilibrium
  - branch      :  0.20 ≤ e < 0.38 → growing, ready for new decisions
  - elevate     :  0.38 ≤ e        → peak coherence, insight available

The classifier computes a composite "basin energy" from the pipeline scores
(reinforcement, leakage, compatibility, strain, pulse strength, synchrony)
and assigns a basin state + updates identity_probability.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BasinState(str, Enum):
    COLLAPSE = "collapse"
    METASTABLE = "metastable"
    STABLE = "stable"
    BRANCH = "branch"
    ELEVATE = "elevate"


# Thresholds (mirroring existence_lab defaults)
_COLLAPSE_THRESHOLD: float = -0.08
_STABLE_THRESHOLD: float = 0.08
_BRANCH_THRESHOLD: float = 0.20
_ELEVATION_THRESHOLD: float = 0.38

# Score weights
_PULSE_WEIGHT: float = 0.30
_COMPAT_WEIGHT: float = 0.12
_STRAIN_WEIGHT: float = 0.15


@dataclass
class BasinInput:
    """Scores from the identity pipeline, fed into the basin classifier."""
    closure_score: float         # 0..1   → acts as reinforcement
    leakage_score: float         # 0..1   → acts as leakage
    compatibility_score: float   # 0..1
    strain_score: float          # 0..1
    pulse_strength: float        # 0..1   → urgency / activation
    # Optional: from InternalWorld
    internal_energy: float = 0.70
    internal_stress: float = 0.10
    # Previous identity_probability (persists across requests)
    prior_identity_probability: float = 0.50


@dataclass
class BasinResult:
    """Output of the basin classifier."""
    basin_state: BasinState
    basin_energy: float            # raw composite energy score
    identity_probability: float    # updated persistence probability
    is_at_risk: bool               # True when collapse or metastable
    guidance_mode: str             # human-readable mode label


def classify_basin(inp: BasinInput) -> BasinResult:
    """
    Compute basin energy and classify the mind's coherence state.

    Y Theory formula: basin_energy = R - L = closure_score - leakage_score.

    That is the complete formula. R is how much the mind is reinforcing
    (closing toward the source). L is how much it is leaking (drifting toward
    an attractor that blocks guidance — shadow).

    States:
      delta_C >= 0.20   ELEVATE   — mind is source-like, radiating
      delta_C >= 0.05   BRANCH    — growing, R clearly exceeds L
      delta_C >  0.0    STABLE    — R > L, coherence holding
      delta_C == 0.0    METASTABLE — balanced at the threshold
      delta_C <  0.0    COLLAPSE  — shadow, L > R, guidance blocked
    """
    basin_energy = inp.closure_score - inp.leakage_score  # delta_C = R - L

    if basin_energy >= 0.20:
        basin_state = BasinState.ELEVATE
    elif basin_energy >= 0.05:
        basin_state = BasinState.BRANCH
    elif basin_energy > 0.0:
        basin_state = BasinState.STABLE
    elif basin_energy == 0.0:
        basin_state = BasinState.METASTABLE
    else:
        basin_state = BasinState.COLLAPSE

    # Identity probability tracks coherence: source-like state builds it,
    # shadow erodes it — both gently, to model hysteresis.
    p = inp.prior_identity_probability
    if basin_state == BasinState.COLLAPSE:
        p = float(max(0.0, p + basin_energy * 0.5))  # erode proportional to depth of shadow
    elif basin_state in (BasinState.BRANCH, BasinState.ELEVATE):
        p = float(min(1.0, p + basin_energy * 0.3))  # build proportional to coherence surplus

    is_at_risk = basin_state in (BasinState.COLLAPSE, BasinState.METASTABLE)

    return BasinResult(
        basin_state=basin_state,
        basin_energy=float(basin_energy),
        identity_probability=p,
        is_at_risk=is_at_risk,
        guidance_mode=_guidance_mode(basin_state),
    )"
BasinClassifier — identity basin state classifier.

Adapted from existence_lab BasinTransitionLayer.

Basin states:
  - collapse    : energy < -0.08   → identity destabilising, high risk
  - metastable  : -0.08 ≤ e < 0.08 → uncertain, needs support
  - stable      :  0.08 ≤ e < 0.20 → healthy equilibrium
  - branch      :  0.20 ≤ e < 0.38 → growing, ready for new decisions
  - elevate     :  0.38 ≤ e        → peak coherence, insight available

The classifier computes a composite "basin energy" from the pipeline scores
(reinforcement, leakage, compatibility, strain, pulse strength, synchrony)
and assigns a basin state + updates identity_probability.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BasinState(str, Enum):
    COLLAPSE = "collapse"
    METASTABLE = "metastable"
    STABLE = "stable"
    BRANCH = "branch"
    ELEVATE = "elevate"


# Thresholds (mirroring existence_lab defaults)
_COLLAPSE_THRESHOLD: float = -0.08
_STABLE_THRESHOLD: float = 0.08
_BRANCH_THRESHOLD: float = 0.20
_ELEVATION_THRESHOLD: float = 0.38

# Score weights
_PULSE_WEIGHT: float = 0.30
_COMPAT_WEIGHT: float = 0.12
_STRAIN_WEIGHT: float = 0.15


@dataclass
class BasinInput:
    """Scores from the identity pipeline, fed into the basin classifier."""
    closure_score: float         # 0..1   → acts as reinforcement
    leakage_score: float         # 0..1   → acts as leakage
    compatibility_score: float   # 0..1
    strain_score: float          # 0..1
    pulse_strength: float        # 0..1   → urgency / activation
    # Optional: from InternalWorld
    internal_energy: float = 0.70
    internal_stress: float = 0.10
    # Previous identity_probability (persists across requests)
    prior_identity_probability: float = 0.50


@dataclass
class BasinResult:
    """Output of the basin classifier."""
    basin_state: BasinState
    basin_energy: float            # raw composite energy score
    identity_probability: float    # updated persistence probability
    is_at_risk: bool               # True when collapse or metastable
    guidance_mode: str             # human-readable mode label


def classify_basin(inp: BasinInput) -> BasinResult:
    """
    Compute basin energy and classify.

    Formula (from existence_lab BasinTransitionLayer.on_step):
        energy = reinforcement + amplitude
                 + pulse_weight  * pulse_strength
                 + compat_weight * compatibility
                 - leakage
                 - strain_weight * strain

    We treat closure_score as reinforcement and map internal_energy as amplitude.
    """
    amplitude = float(inp.internal_energy - 0.5)   # centre at 0

    basin_energy = (
        inp.closure_score                            # reinforcement
        + amplitude                                  # amplitude from InternalWorld
        + _PULSE_WEIGHT  * inp.pulse_strength
        + _COMPAT_WEIGHT * inp.compatibility_score
        - inp.leakage_score                          # leakage
        - _STRAIN_WEIGHT * inp.strain_score
        - 0.08 * inp.internal_stress                 # internal stress drag
    )

    # Classify
    if basin_energy < _COLLAPSE_THRESHOLD:
        basin_state = BasinState.COLLAPSE
    elif basin_energy < _STABLE_THRESHOLD:
        basin_state = BasinState.METASTABLE
    elif basin_energy < _BRANCH_THRESHOLD:
        basin_state = BasinState.STABLE
    elif basin_energy < _ELEVATION_THRESHOLD:
        basin_state = BasinState.BRANCH
    else:
        basin_state = BasinState.ELEVATE

    # Update identity_probability (hysteresis from existence_lab)
    p = inp.prior_identity_probability
    if basin_state == BasinState.COLLAPSE:
        p = float(max(0.0, p - 0.05))
    elif basin_state == BasinState.ELEVATE:
        p = float(min(1.0, p + 0.03))
    # else: unchanged

    is_at_risk = basin_state in (BasinState.COLLAPSE, BasinState.METASTABLE)

    guidance_mode = _guidance_mode(basin_state)

    return BasinResult(
        basin_state=basin_state,
        basin_energy=float(basin_energy),
        identity_probability=p,
        is_at_risk=is_at_risk,
        guidance_mode=guidance_mode,
    )


def _guidance_mode(basin_state: BasinState) -> str:
    return {
        BasinState.COLLAPSE:    "EMERGENCY — identity under severe stress; prioritise stabilisation",
        BasinState.METASTABLE:  "SUPPORT — identity is fragile; gentle grounding needed",
        BasinState.STABLE:      "GUIDANCE — identity is stable; balanced advice is appropriate",
        BasinState.BRANCH:      "GROWTH — identity is resilient; help explore options",
        BasinState.ELEVATE:     "INSIGHT — identity is coherent; deep reflection is possible",
    }[basin_state]



