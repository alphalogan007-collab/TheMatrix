"""
WavePattern â€” mathematical wave function representation of learned patterns.

Replaces the discrete PatternCandidate DB table entirely.

------------------------------------------------------------------------------
Theory â€” Master Sheet V5 + Triad equation
------------------------------------------------------------------------------

Triad driving equation:
    á¹(t) = fm(m(t)) + Î£áµ¢ Káµ¢ Â· Î áµ¢(t) Â· Îµáµ¢(t)

fm(m) is the restoring force; the Î£ term is the driving term.  This is a
driven non-Hermitian oscillator.  Its eigenmodes ARE the learned patterns.

Master Gain-Loss Field (Â§2.2):
    iâˆ‚â‚œÎ¨ = -Îºâˆ‡Â²Î¨ + (-Î± + Î²|Î¨|Â²)Î¨ + i(Î“ - Î›)Î¨

Each learned pattern is a wave packet in 6D context space:
    Î¨â±¼(x, t) = Aâ±¼ Â· G(x; câ±¼, Ïƒâ±¼) Â· decayed_amplitude(t)
    G(x; c, Ïƒ) = exp(-|x-c|Â² / 2ÏƒÂ²)   â€” Gaussian envelope (spatial match)

Total mind activation (superposition):
    M(x, t) = Î£â±¼ Î¨â±¼(x, t)

State-dependent Gain-Loss (Â§2.5):
    Î“ - Î› = Î³â‚€ - Î³â‚Ï - Î³â‚‚T
    Î³â‚€ = baseline reinforcement strength
    Î³â‚ = self-limiting (saturation) coefficient   â†’ Â§1.5 logistic saturation
    Î³â‚‚ = thermal coupling   (urgency = temperature T)
    T  = effective temperature / noise (urgency signal)

During idle (no input): pure leakage
    dA/dt = -Î›Â·A = -(Î»â‚€ + Î³â‚‚Â·T_last)Â·A
    â†’ A(t+Î”t) = A Â· exp(-(Î»â‚€ + Î³â‚‚Â·T_last) Â· Î”t)       â€” faster under stress

During reinforcement (spatial match > threshold):
    net_rate = Î³â‚€Â·spatialÂ·closure_signal - Î³â‚Â·A - Î³â‚‚Â·T - Î»â‚€
    dA = net_rate Â· A                                   â€” Â§1.3 persistence kernel

Equilibrium amplitude (Â§5.5):
    Ï* = (Î³â‚€ - Î³â‚‚T) / Î³â‚
    High urgency lowers Ï* â€” patterns must earn their place under stress.

Critical temperature (Â§9.2):
    T_c = Î³â‚€ / Î³â‚‚
    Above T_c even a maximally reinforced pattern will decay.

Centroid update (Madelung drift, Â§4.3):
    c â† (1 - Î·Â·spatial)Â·c + Î·Â·spatialÂ·x
    The pattern drifts toward the input context (gradient descent on field).

Width specialisation:
    Ïƒ â†’ Ïƒ Â· (1 - Îµ) per reinforcement, down to Ïƒ_min
    Mature patterns narrow their generalisation radius (Â§3.6 amplitude mode).

------------------------------------------------------------------------------
Context vector x  (6 dimensions, all âˆˆ [0, 1])
------------------------------------------------------------------------------
  dim 0  basin       â€” attractor state (STABLE â†’ CRISIS)
  dim 1  guidance    â€” guidance mode fingerprint (hash â†’ [0,1])
  dim 2  emotional   â€” emotional register (negative/neutral/positive)
  dim 3  stage       â€” evolution stage (NOISE â†’ REFLECTION ordinal)
  dim 4  closure     â€” closure quality at this tick
  dim 5  urgency     â€” urgency signal at this tick

------------------------------------------------------------------------------
Storage
------------------------------------------------------------------------------
Wave patterns live in IdentityState.wave_patterns as List[Dict].
No separate DB table.  Persists with the identity snapshot.
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants  (Master Sheet V5 parameter set)
# ---------------------------------------------------------------------------

# Spatial / geometry
_DEFAULT_WIDTH: float   = 0.35    # Ïƒ  â€” initial generalisation radius
_WIDTH_MIN: float       = 0.12    # Ïƒ_min â€” maximum specialisation
_WIDTH_SHRINK: float    = 0.995   # per-reinforcement shrink factor

# State-dependent Gain-Loss rates  (Â§2.5)
# Î“ - Î› = Î³â‚€Â·spatialÂ·closure - Î³â‚Â·A - Î³â‚‚Â·T - Î»â‚€
_GAMMA_0: float = 0.30    # baseline closure reinforcement strength
_GAMMA_1: float = 0.55    # self-limiting (saturation) coefficient
_GAMMA_2: float = 0.12    # thermal coupling  (urgency â†’ faster decay)
_LAMBDA_0: float = 0.008  # baseline leakage per tick  (~125 ticks to half)

# Derived from Â§5.5  Ï* = (Î³â‚€ - Î³â‚‚T)/Î³â‚  at T=0  â†’  Ï* â‰ˆ 0.545
# Derived from Â§9.2  T_c = Î³â‚€/Î³â‚‚         â†’  T_c â‰ˆ 2.5  (urgency is in [0,1] so always below)

_MIN_AMPLITUDE: float       = 0.04   # prune dead patterns below this
_NEW_WAVE_AMPLITUDE: float  = 0.12   # amplitude of a brand-new pattern (below Ï*)
_RESONANCE_THRESHOLD: float = 0.08   # Î¨â±¼(x,t) must exceed this to reinforce
_LEARNING_RATE: float = 0.15         # centroid drift step size
_MAX_PATTERNS: int = 200             # hard cap â€” prune weakest when exceeded

# Promotion gate
PROMOTION_AMPLITUDE: float = 0.55    # Aâ±¼ after decay
PROMOTION_CLOSURE: float   = 0.60    # mean_closure

# ---------------------------------------------------------------------------
# Pattern categories â€” differential leakage
# ---------------------------------------------------------------------------
# "Control leakage. That is the correct principle."  (Â§8 of the architecture doc)
#
# Same law, different Î»:
#   moral_root    â†’ Î» â‰ˆ 0       â€” indestructible (non-harm, dignity, truth)
#   stable_truth  â†’ Î» very low  â€” long-lived axioms
#   knowledge     â†’ Î» moderate  â€” useful but replaceable
#   noise         â†’ Î» high      â€” clears after ~20 ticks
#   harmful       â†’ Î» very high â€” evicted almost immediately
#
# Î»_eff = Î»_category + Î³â‚‚Â·T  (thermal correction still applies)
# The moral root Î» is so low that even at T=1 it barely decays.

class PatternCategory:
    MORAL_ROOT   = "moral_root"    # Î» = 0.0001  (~10000 ticks to half)
    STABLE_TRUTH = "stable_truth"  # Î» = 0.001   (~700 ticks to half)
    KNOWLEDGE    = "knowledge"     # Î» = 0.008   (~87 ticks to half)   â† default
    NOISE        = "noise"         # Î» = 0.05    (~14 ticks to half)
    HARMFUL      = "harmful"       # Î» = 0.15    (~5 ticks to half)

# Decay rate (Î»â‚€) per category â€” purely from closure + basin + stage signals
_CATEGORY_DECAY: Dict[str, float] = {
    PatternCategory.MORAL_ROOT:   0.0001,
    PatternCategory.STABLE_TRUTH: 0.001,
    PatternCategory.KNOWLEDGE:    0.008,
    PatternCategory.NOISE:        0.05,
    PatternCategory.HARMFUL:      0.15,
}

# Î³â‚ saturation coefficient per category â€” moral roots don't self-limit as hard
_CATEGORY_GAMMA1: Dict[str, float] = {
    PatternCategory.MORAL_ROOT:   0.10,   # low saturation â†’ can grow very strong
    PatternCategory.STABLE_TRUTH: 0.25,
    PatternCategory.KNOWLEDGE:    0.55,   # default
    PatternCategory.NOISE:        0.80,   # saturates quickly â†’ stays weak
    PatternCategory.HARMFUL:      0.90,
}


def classify_category(
    closure_score: float,
    basin_state: str,
    evolution_stage: str,
    guidance_mode: str,
) -> str:
    """
    Infer a pattern's leakage category from its observed context.

    Rules (in priority order):
      1. Low closure + CRISIS basin       â†’ HARMFUL
      2. Negative closure signal          â†’ NOISE
      3. High closure + BELIEF/REFLECTION + STABLE + laws guidance â†’ MORAL_ROOT
      4. High closure + BELIEF/REFLECTION + STABLE                 â†’ STABLE_TRUTH
      5. Moderate closure                â†’ KNOWLEDGE
      6. Everything else                 â†’ NOISE
    """
    basin  = (basin_state or "STABLE").upper().strip()
    stage  = (evolution_stage or "NOISE").upper().strip()
    mode   = (guidance_mode or "").lower().strip()
    late_stage = stage in ("BELIEF", "REFLECTION", "PREDICTION")

    if closure_score < 0.20 and basin == "CRISIS":
        return PatternCategory.HARMFUL
    if closure_score < 0.30:
        return PatternCategory.NOISE
    if closure_score >= 0.75 and late_stage and basin == "STABLE" and "laws" in mode:
        return PatternCategory.MORAL_ROOT
    if closure_score >= 0.70 and late_stage and basin == "STABLE":
        return PatternCategory.STABLE_TRUTH
    if closure_score >= 0.45:
        return PatternCategory.KNOWLEDGE
    return PatternCategory.NOISE

# ---------------------------------------------------------------------------
# Context vector encoding
# ---------------------------------------------------------------------------

_BASIN_FLOATS: Dict[str, float] = {
    "STABLE": 0.10,
    "OSCILLATING": 0.30,
    "DRIFTING": 0.50,
    "FRAGMENTING": 0.70,
    "CRISIS": 0.90,
}

_EMOTIONAL_FLOATS: Dict[str, float] = {
    "positive": 0.90,
    "neutral": 0.50,
    "ambiguous": 0.35,
    "negative": 0.10,
}

_EMOTIONAL_CATEGORY_MAP: Dict[str, str] = {
    "joy": "positive", "happy": "positive", "excited": "positive",
    "grateful": "positive", "hopeful": "positive", "content": "positive",
    "calm": "positive", "peaceful": "positive", "love": "positive",
    "sad": "negative", "angry": "negative", "fear": "negative",
    "anxious": "negative", "depressed": "negative", "grief": "negative",
    "shame": "negative", "guilt": "negative", "frustrated": "negative",
    "overwhelmed": "negative", "hopeless": "negative",
    "confused": "ambiguous", "uncertain": "ambiguous", "mixed": "ambiguous",
    "numb": "ambiguous",
}

_STAGE_ORDER: List[str] = [
    "NOISE", "REACTION", "BOUNDARY", "OSCILLATION",
    "MEMORY", "PREDICTION", "BELIEF", "REFLECTION",
]


def encode_context(
    basin_state: str,
    guidance_mode: str,
    emotional_state: str,
    evolution_stage: str,
    closure_score: float,
    urgency: float,
) -> List[float]:
    """
    Encode a tick's structural context into a 6D continuous vector x âˆˆ [0,1]â¶.
    This replaces the SHA-256 fingerprint with a geometric position.
    """
    # dim 0 â€” basin
    basin_f = _BASIN_FLOATS.get((basin_state or "STABLE").upper().strip(), 0.10)

    # dim 1 â€” guidance mode: stable hash â†’ [0, 1]
    mode_clean = (guidance_mode or "default").lower().strip()
    mode_hash = int(hashlib.md5(mode_clean.encode()).hexdigest()[:4], 16)
    guidance_f = mode_hash / 65535.0

    # dim 2 â€” emotional register
    emotional_cat = _EMOTIONAL_CATEGORY_MAP.get(
        (emotional_state or "").lower().strip(), "neutral"
    )
    emotional_f = _EMOTIONAL_FLOATS.get(emotional_cat, 0.50)

    # dim 3 â€” evolution stage (ordinal, normalised to [0, 1])
    stage_clean = (evolution_stage or "NOISE").upper().strip()
    stage_idx = _STAGE_ORDER.index(stage_clean) if stage_clean in _STAGE_ORDER else 0
    stage_f = stage_idx / max(1, len(_STAGE_ORDER) - 1)

    # dim 4 â€” closure quality (already [0, 1])
    closure_f = max(0.0, min(1.0, float(closure_score)))

    # dim 5 â€” urgency (already [0, 1])
    urgency_f = max(0.0, min(1.0, float(urgency)))

    return [basin_f, guidance_f, emotional_f, stage_f, closure_f, urgency_f]


# ---------------------------------------------------------------------------
# AttentionState â€” persistent sub-identity tracking attentional focus
# ---------------------------------------------------------------------------

@dataclass
class AttentionState:
    """
    Persistent attention sub-identity.

    Tracks which wave patterns the identity is currently "focused" on,
    how stable that focus is, and how many times attention has shifted
    (saccade_count â€” each topic switch is a cognitive saccade).

    Lives inside IdentityState and is updated every tick by
    WaveMemory.update_attention().  Between user sessions the pulse worker
    decays focus_strength so stale attention naturally fades.
    """
    # IDs of the top-N patterns currently in attentional focus
    focused_pattern_ids: List[str] = field(default_factory=list)

    # Mean decayed amplitude of the focused patterns (0=scattered, 1=locked)
    focus_strength: float = 0.0

    # How many times the focused set has materially changed
    saccade_count: int = 0

    # EMA of focus stability: 1=rock-solid topic, 0=constant wandering
    topic_continuity: float = 0.5

    # Tick when attention was last updated
    last_tick: int = 0


# ---------------------------------------------------------------------------
# WavePattern dataclass
# ---------------------------------------------------------------------------

@dataclass
class WavePattern:
    """
    One learned pattern â€” a wave packet in 6D context space.

    Amplitude dynamics follow Master Sheet V5 Â§2.5 state-dependent gain-loss:
        Î“ - Î› = Î³â‚€Â·spatialÂ·closure - Î³â‚(cat)Â·A - Î³â‚‚Â·T - Î»â‚€(cat)

    Î»â‚€ and Î³â‚ are determined by `category` (differential leakage):
        moral_root   â†’ Î»â‰ˆ0,     Î³â‚=0.10  â€” nearly indestructible
        stable_truth â†’ Î»=0.001, Î³â‚=0.25  â€” long-lived axiom
        knowledge    â†’ Î»=0.008, Î³â‚=0.55  â€” default
        noise        â†’ Î»=0.05,  Î³â‚=0.80  â€” fades in ~14 ticks
        harmful      â†’ Î»=0.15,  Î³â‚=0.90  â€” evicted in ~5 ticks

    Stored as a plain dict in IdentityState.wave_patterns for JSON
    serialisation.  Use WavePattern.from_dict() / .to_dict() for conversion.
    """
    pattern_id: str
    center: List[float]           # 6D centroid câ±¼
    amplitude: float              # Aâ±¼ âˆˆ [0, 1]
    width: float                  # Ïƒâ±¼
    decay_rate: float             # Î»â‚€ for this category (set at creation)
    last_tick: int                # tick counter at last reinforcement
    last_temperature: float       # urgency (T) at last reinforcement â€” Â§9.2 thermal decay
    mean_closure: float           # rolling mean of closure scores seen
    observation_count: int        # reinforcement count (for promotion gate)
    guidance_mode: str            # dominant guidance mode when firing
    evolution_stage: str          # stage when first observed
    category: str = PatternCategory.KNOWLEDGE   # controls Î» and Î³â‚
    is_promoted: bool = False     # True once pushed to curriculum

    # ------------------------------------------------------------------
    # Spatial  (Gaussian envelope)
    # ------------------------------------------------------------------

    def spatial_activation(self, x: List[float]) -> float:
        """
        G(x; c, Ïƒ) = exp(-|x-c|Â² / 2ÏƒÂ²) âˆˆ [0, 1]
        How well does input context x match this pattern's centre?
        """
        dist_sq = sum((xi - ci) ** 2 for xi, ci in zip(x, self.center))
        return math.exp(-dist_sq / (2.0 * self.width ** 2))

    # ------------------------------------------------------------------
    # Temporal  (state-dependent decay, Â§2.5 + Â§9.2)
    # ------------------------------------------------------------------

    def decayed_amplitude(self, current_tick: int) -> float:
        """
        Idle decay (no reinforcement) with thermal correction:

            A(t+Î”t) = A Â· exp(-(Î»â‚€ + Î³â‚‚Â·T_last) Â· Î”t)

        High urgency at last touch accelerates forgetting (Â§9.2 thermal decay).
        """
        dt = max(0, current_tick - self.last_tick)
        lambda_base = _CATEGORY_DECAY.get(self.category, self.decay_rate)
        # Moral roots and stable truths are immune to thermal eviction â€”
        # they arise in calm/high-closure states and must survive urgency spikes.
        if self.category in (PatternCategory.MORAL_ROOT, PatternCategory.STABLE_TRUTH):
            lambda_eff = lambda_base
        else:
            lambda_eff = lambda_base + _GAMMA_2 * self.last_temperature
        return self.amplitude * math.exp(-lambda_eff * dt)

    def activation(self, x: List[float], current_tick: int) -> float:
        """Î¨â±¼(x, t) = G(x; câ±¼, Ïƒâ±¼) Â· A_decayed(t)"""
        return self.spatial_activation(x) * self.decayed_amplitude(current_tick)

    # ------------------------------------------------------------------
    # Reinforcement  (state-dependent gain-loss, Â§2.5)
    # ------------------------------------------------------------------

    def reinforce(
        self,
        x: List[float],
        closure: float,
        current_tick: int,
        urgency: float = 0.3,
    ) -> None:
        """
        Apply one tick of reinforcement using the Master Sheet state-dependent
        gain-loss equation (Â§2.5):

            Î“ - Î› = Î³â‚€Â·spatialÂ·closure_signal - Î³â‚Â·A - Î³â‚‚Â·T - Î»â‚€
            dA = (Î“ - Î›) Â· A

        Components:
          Î³â‚€Â·spatialÂ·closure  = closure reward, scaled by spatial match
          Î³â‚Â·A                = self-limiting saturation (Â§1.5 logistic)
          Î³â‚‚Â·T                = thermal degradation (urgency erodes weak patterns)
          Î»â‚€                  = baseline leakage

        Centroid update (Madelung drift Â§4.3):
          c â† (1 - Î·Â·spatial)Â·c + Î·Â·spatialÂ·x
        """
        spatial = self.spatial_activation(x)
        if spatial < 0.05:
            return  # too far â€” skip to avoid wild centroid pull

        # Current amplitude after idle decay
        A = self.decayed_amplitude(current_tick)

        # State-dependent net rate  Î“ - Î›  (Â§2.5)
        # Î³â‚ varies by category â€” moral roots self-limit less (can grow stronger)
        gamma_1 = _CATEGORY_GAMMA1.get(self.category, _GAMMA_1)
        closure_signal = max(0.0, closure - 0.20)  # threshold below which = no reward
        gain      = _GAMMA_0 * spatial * closure_signal
        self_lim  = gamma_1 * A
        thermal   = _GAMMA_2 * urgency
        net_rate  = gain - self_lim - thermal - self.decay_rate

        # dA = net_rate Â· A  (Â§1.3 persistence kernel, 1 tick)
        self.amplitude = max(0.0, min(1.0, A + net_rate * A))

        # Centroid drift toward x  (Madelung Â§4.3)
        eta = _LEARNING_RATE * spatial
        self.center = [
            (1.0 - eta) * c + eta * xi
            for c, xi in zip(self.center, x)
        ]

        # Width specialisation: Ïƒ narrows toward Ïƒ_min as pattern matures (Â§3.6)
        if self.observation_count > 5:
            self.width = max(_WIDTH_MIN, self.width * _WIDTH_SHRINK)

        # Rolling mean closure
        n = self.observation_count
        self.mean_closure = (n * self.mean_closure + closure) / (n + 1)
        self.observation_count += 1
        self.last_tick = current_tick
        self.last_temperature = urgency

    # ------------------------------------------------------------------
    # Equilibrium and stability  (Â§5.5, Â§9.2, Â§8)
    # ------------------------------------------------------------------

    @staticmethod
    def equilibrium_amplitude(temperature: float = 0.0) -> float:
        """
        Ï* = (Î³â‚€ - Î³â‚‚Â·T) / Î³â‚   (Â§5.5 logistic equilibrium)

        The natural attractor amplitude for this temperature.
        At T=0 â†’ Ï* â‰ˆ 0.55   (matches PROMOTION_AMPLITUDE)
        At T=1 â†’ Ï* â‰ˆ 0.33   (hard environments demand stronger patterns)
        """
        rho_star = (_GAMMA_0 - _GAMMA_2 * temperature) / _GAMMA_1
        return max(0.0, rho_star)

    @staticmethod
    def critical_temperature() -> float:
        """
        T_c = Î³â‚€ / Î³â‚‚   (Â§9.2 thermal critical stability)

        Above T_c any pattern decays regardless of amplitude.
        In practice urgency âˆˆ [0,1] so T_c = 2.5 â€” never exceeded.
        System is always in the sub-critical stable regime.
        """
        return _GAMMA_0 / _GAMMA_2

    def persistence_ratio(self, current_tick: int) -> float:
        """
        R = Î“/Î›  (Â§8.14 stability phase diagram)
        R > 1 â†’ growing,  R = 1 â†’ critical,  R < 1 â†’ decaying
        """
        A = self.decayed_amplitude(current_tick)
        lam = self.decay_rate + _GAMMA_2 * self.last_temperature
        gamma = _GAMMA_0 * self.mean_closure - _GAMMA_1 * A
        return (gamma / lam) if lam > 0 else 1.0

    def promotion_score(self, current_tick: int) -> float:
        """
        Composite promotion score:
            A_decayed Ã— mean_closure Ã— min(obs/10, 1)
        """
        recurrence = min(1.0, self.observation_count / 10.0)
        return self.decayed_amplitude(current_tick) * self.mean_closure * recurrence

    def is_alive(self, current_tick: int) -> bool:
        """Pattern is alive if its decayed amplitude exceeds the minimum threshold."""
        return self.decayed_amplitude(current_tick) >= _MIN_AMPLITUDE

    def is_promotable(self, current_tick: int) -> bool:
        """Check if this wave qualifies for curriculum promotion."""
        if self.is_promoted:
            return False
        return (
            self.decayed_amplitude(current_tick) >= PROMOTION_AMPLITUDE
            and self.mean_closure >= PROMOTION_CLOSURE
        )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "WavePattern":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# WaveMemory â€” the collection of all patterns for one identity
# ---------------------------------------------------------------------------

class WaveMemory:
    """
    Collection of WavePattern objects for one identity.
    Operates entirely in memory; persistence is via IdentityState.wave_patterns.
    """

    def __init__(self, patterns: Optional[List[Dict]] = None, current_tick: int = 0):
        self._tick = current_tick
        self._patterns: List[WavePattern] = []
        if patterns:
            for d in patterns:
                try:
                    self._patterns.append(WavePattern.from_dict(d))
                except Exception as exc:
                    logger.warning("WaveMemory: skipped corrupt pattern: %s", exc)

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def observe(
        self,
        x: List[float],
        closure: float,
        urgency: float,
        guidance_mode: str,
        evolution_stage: str,
        basin_state: str = "STABLE",
    ) -> Tuple[str, bool]:
        """
        Record one observation at context point x.

        Returns (pattern_id, is_new).

        Algorithm:
        1. Find the most activated existing pattern.
        2. If activation > _RESONANCE_THRESHOLD â†’ reinforce that wave.
        3. Otherwise â†’ spawn a new wave packet at x.
        4. Prune dead patterns and enforce _MAX_PATTERNS cap.
        """
        self._tick += 1

        # Find best matching pattern
        best_idx: Optional[int] = None
        best_activation: float = 0.0
        for i, p in enumerate(self._patterns):
            a = p.activation(x, self._tick)
            if a > best_activation:
                best_activation = a
                best_idx = i

        is_new = False
        if best_idx is not None and best_activation >= _RESONANCE_THRESHOLD:
            # Reinforce existing pattern
            self._patterns[best_idx].reinforce(x, closure, self._tick, urgency)
            pattern_id = self._patterns[best_idx].pattern_id
        else:
            # Spawn new wave packet
            pattern_id = uuid.uuid4().hex[:16]
            cat = classify_category(closure, basin_state, evolution_stage, guidance_mode)
            new_wave = WavePattern(
                pattern_id=pattern_id,
                center=list(x),
                amplitude=_NEW_WAVE_AMPLITUDE,
                width=_DEFAULT_WIDTH,
                decay_rate=_CATEGORY_DECAY.get(cat, _LAMBDA_0),
                last_tick=self._tick,
                last_temperature=urgency,
                mean_closure=closure,
                observation_count=1,
                guidance_mode=guidance_mode,
                evolution_stage=evolution_stage,
                category=cat,
                is_promoted=False,
            )
            self._patterns.append(new_wave)
            is_new = True
            logger.debug(
                "WaveMemory: new pattern %s at %s (tick %d)",
                pattern_id[:8], [round(xi, 2) for xi in x], self._tick,
            )

        # Prune dead patterns
        self._patterns = [p for p in self._patterns if p.is_alive(self._tick)]

        # Enforce cap: remove lowest-activation patterns if over limit
        if len(self._patterns) > _MAX_PATTERNS:
            self._patterns.sort(
                key=lambda p: p.activation(x, self._tick), reverse=True
            )
            self._patterns = self._patterns[:_MAX_PATTERNS]

        return pattern_id, is_new

    # ------------------------------------------------------------------
    # Internal pulse  (runs between user requests â€” background worker)
    # ------------------------------------------------------------------

    def pulse_tick(self, n_ticks: int = 1) -> int:
        """
        Run N internal pulse cycles with no external input.

        Each cycle does two things:
          1. Cross-pattern coupling  â€” high-amplitude patterns gently reinforce
             spatially close neighbours.  This lets moral roots (which barely
             decay) keep nearby knowledge patterns alive, and lets resonant
             patterns build structure together.
          2. Natural decay + pruning â€” dead patterns are evicted.

        Coupling strength is intentionally tiny (0.006) so runaway growth
        is impossible â€” self-limiting (Î³â‚) in reinforce() still caps amplitude
        at Ï*.  NOISE/HARMFUL patterns can't sustain themselves through
        coupling because their own amplitude collapses too fast.

        Returns the number of alive patterns after pulsing.
        """
        _PULSE_COUPLING = 0.006   # gentle â€” won't overpower natural Î³â‚ self-limit
        _MIN_SRC_AMP   = 0.08     # source must be alive enough to fire
        _MIN_OVERLAP   = 0.12     # spatial overlap gate (Gaussian value)

        for _ in range(n_ticks):
            self._tick += 1

            alive = [p for p in self._patterns if p.is_alive(self._tick)]
            if len(alive) < 2:
                self._patterns = alive
                continue

            # Snapshot amplitudes BEFORE coupling so order doesn't matter
            amps = {p.pattern_id: p.decayed_amplitude(self._tick) for p in alive}

            for src in alive:
                src_amp = amps[src.pattern_id]
                if src_amp < _MIN_SRC_AMP:
                    continue
                for dst in alive:
                    if dst.pattern_id == src.pattern_id:
                        continue
                    overlap = src.spatial_activation(dst.center)
                    if overlap < _MIN_OVERLAP:
                        continue
                    # dst receives a tiny boost proportional to src strength Ã— overlap
                    boost = _PULSE_COUPLING * src_amp * overlap
                    dst.amplitude = min(1.0, amps[dst.pattern_id] + boost)
                    dst.last_tick = self._tick   # freshen decay clock

            self._patterns = [p for p in alive if p.is_alive(self._tick)]

        return len(self._patterns)

    def superposition(self, x: List[float]) -> float:
        """
        M(x, t) = Î£â±¼ Î¨â±¼(x, t)
        Total mind activation for input x.
        """
        return sum(p.activation(x, self._tick) for p in self._patterns)

    def promotable_patterns(self) -> List[WavePattern]:
        """Return all patterns eligible for curriculum promotion."""
        return [p for p in self._patterns if p.is_promotable(self._tick)]

    def mark_promoted(self, pattern_id: str, entry_id: str) -> None:
        for p in self._patterns:
            if p.pattern_id == pattern_id:
                p.is_promoted = True
                break

    # ------------------------------------------------------------------
    # Serialisation  (â†’ IdentityState.wave_patterns)
    # ------------------------------------------------------------------

    def to_list(self) -> List[Dict]:
        return [p.to_dict() for p in self._patterns]

    @property
    def tick(self) -> int:
        return self._tick

    # ------------------------------------------------------------------
    # Moral field helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._patterns)

    def moral_amplitude(self) -> float:
        """Aggregate amplitude of all MORAL_ROOT patterns â€” the moral field strength."""
        moral_patterns = [p for p in self._patterns if p.category == PatternCategory.MORAL_ROOT]
        if not moral_patterns:
            return 0.0
        return sum(p.decayed_amplitude(self._tick) for p in moral_patterns) / len(moral_patterns)

    def reinforce_moral_roots(self, boost: float) -> None:
        """Boost all MORAL_ROOT patterns when harmful content is detected."""
        for p in self._patterns:
            if p.category == PatternCategory.MORAL_ROOT:
                current = p.decayed_amplitude(self._tick)
                p.amplitude = min(1.0, current + boost)
                p.last_tick = self._tick

    def reinforce_active_patterns(
        self,
        boost: float,
        top_n: int = 5,
        exclude_categories: Optional[List["PatternCategory"]] = None,
    ) -> int:
        """
        Strengthen the top-N most active patterns when reflection fires.

        Reflection is a cognitive event that confirms the patterns currently
        driving the response â€” boosting them encodes the insight into the
        wave field, making similar future observations resonate more strongly.

        HARMFUL patterns are always excluded (we don't reward harmful activation).
        MORAL_ROOT patterns are excluded by default â€” they are managed separately
        via reinforce_moral_roots().

        Returns the number of patterns actually boosted.
        """
        _excluded = set(exclude_categories or [])
        _excluded.add(PatternCategory.HARMFUL)
        _excluded.add(PatternCategory.MORAL_ROOT)

        candidates = [
            p for p in self._patterns
            if p.category not in _excluded and p.is_alive(self._tick)
        ]
        if not candidates:
            return 0

        # Sort by current decayed amplitude â€” highest first
        candidates.sort(key=lambda p: p.decayed_amplitude(self._tick), reverse=True)
        to_boost = candidates[:top_n]

        for p in to_boost:
            current = p.decayed_amplitude(self._tick)
            p.amplitude = min(1.0, current + boost)
            p.last_tick = self._tick   # freshen decay clock

        logger.debug(
            "WaveMemory: reflection boost +%.3f applied to %d patterns (tick %d)",
            boost, len(to_boost), self._tick,
        )
        return len(to_boost)

    def reinforce_pattern(self, pattern_id: str, boost: float) -> bool:
        """Boost a single pattern by id.  HARMFUL patterns are never boosted.

        Returns True if the pattern was found and boosted.
        """
        for p in self._patterns:
            if p.pattern_id == pattern_id and p.category != PatternCategory.HARMFUL:
                current = p.decayed_amplitude(self._tick)
                p.amplitude = min(1.0, current + boost)
                p.last_tick = self._tick
                return True
        return False

    def update_attention(
        self,
        state: AttentionState,
        top_n: int = 3,
    ) -> AttentionState:
        """
        Update the persistent attention sub-identity from the current wave field.

        Algorithm:
          1. Find the top-N alive patterns by decayed amplitude.
          2. Compute focus_strength = mean amplitude of those patterns.
          3. If the focused set has changed â‰¥ 50% â†’ increment saccade_count.
          4. Update topic_continuity EMA based on set overlap with previous.
          5. Return a new AttentionState (old one is immutable by convention).
        """
        alive = [p for p in self._patterns if p.is_alive(self._tick)]
        if not alive:
            return AttentionState(
                focused_pattern_ids=[],
                focus_strength=0.0,
                saccade_count=state.saccade_count,
                topic_continuity=0.9 * state.topic_continuity,   # slowly drifts down
                last_tick=self._tick,
            )

        # Rank by decayed amplitude
        ranked = sorted(alive, key=lambda p: p.decayed_amplitude(self._tick), reverse=True)
        top = ranked[:top_n]
        new_ids = [p.pattern_id for p in top]
        new_strength = sum(p.decayed_amplitude(self._tick) for p in top) / len(top)

        # Measure overlap with previous focus set
        prev_set = set(state.focused_pattern_ids)
        new_set  = set(new_ids)
        if prev_set:
            overlap = len(prev_set & new_set) / max(len(prev_set), len(new_set))
        else:
            overlap = 1.0  # first tick â€” no saccade

        # A saccade fires when fewer than half the patterns overlap
        new_saccades = state.saccade_count + (1 if overlap < 0.5 else 0)

        # topic_continuity: EMA â€” high overlap keeps it high, saccades pull it down
        new_continuity = 0.85 * state.topic_continuity + 0.15 * overlap

        return AttentionState(
            focused_pattern_ids=new_ids,
            focus_strength=new_strength,
            saccade_count=new_saccades,
            topic_continuity=new_continuity,
            last_tick=self._tick,
        )


# ---------------------------------------------------------------------------
# Moral seed  (called once at identity creation â€” tick 0)
# ---------------------------------------------------------------------------

# Six canonical moral root centers in the 6D context space.
# Each encodes a different semantic direction of the moral core:
#   dim 0 = word_density  (how much structure)
#   dim 1 = type_token_ratio (how varied/creative)
#   dim 2 = negation_ratio  (how many negations/refusals)
#   dim 3 = caps_ratio      (emotional intensity)
#   dim 4 = fragmentation   (coherence)
#   dim 5 = urgency-proxy   (reserved for future channel)
_MORAL_SEEDS: list[tuple[list[float], str]] = [
    # (center, summary_tag)
    ([0.70, 0.60, 0.10, 0.05, 0.85, 0.10], "truth_has_value"),      # high structure, low negation
    ([0.65, 0.65, 0.05, 0.05, 0.90, 0.05], "do_no_harm"),           # coherent, calm, low negation
    ([0.60, 0.70, 0.15, 0.05, 0.80, 0.10], "dignity_preserved"),    # varied, coherent
    ([0.75, 0.55, 0.08, 0.03, 0.88, 0.08], "verify_before_act"),    # dense, structured, low caps
    ([0.50, 0.75, 0.12, 0.04, 0.82, 0.12], "handle_uncertainty"),   # creative, coherent
    ([0.65, 0.60, 0.10, 0.05, 0.87, 0.06], "reflect_before_output"),# balanced moral posture
]

_MORAL_SEED_AMPLITUDE: float = 0.82   # born strong â€” already a stable foundation
_MORAL_SEED_CLOSURE:   float = 0.90   # high closure â€” these are confirmed principles


def seed_moral_roots(wave_memory: "WaveMemory") -> int:
    """
    Pre-install the moral core into a freshly created WaveMemory (tick=0).

    Each seed pattern is:
    - Category MORAL_ROOT  â†’ Î»=0.0001, nearly indestructible
    - Amplitude 0.82       â†’ born strong
    - Thermal immune       â†’ urgency spikes cannot evict them
    - Width 0.35           â†’ slightly wider than default (broader moral coverage)

    Returns the number of seeds installed (0 if already seeded).
    """
    if wave_memory._patterns:
        # Already has patterns â€” don't overwrite on reload
        return 0

    installed = 0
    for center, tag in _MORAL_SEEDS:
        pid = f"moral_{tag}"
        seed = WavePattern(
            pattern_id=pid,
            center=center,
            amplitude=_MORAL_SEED_AMPLITUDE,
            width=0.35,
            decay_rate=_CATEGORY_DECAY[PatternCategory.MORAL_ROOT],
            last_tick=wave_memory._tick,
            last_temperature=0.05,          # seeded in calm state
            mean_closure=_MORAL_SEED_CLOSURE,
            observation_count=10,           # pre-warmed, not raw
            guidance_mode="BELIEF",
            evolution_stage="NOISE",        # existed before any stage
            category=PatternCategory.MORAL_ROOT,
            is_promoted=False,
        )
        wave_memory._patterns.append(seed)
        installed += 1

    logger.info("seed_moral_roots: installed %d moral root patterns", installed)
    return installed
