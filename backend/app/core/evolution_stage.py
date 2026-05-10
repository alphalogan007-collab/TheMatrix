"""
EvolutionStage â€” the 8-stage identity evolution ladder.

Derived directly from the MindAI foundational documents:
  - EVOLUTION: From Persistence to Awareness (25 chapters)
  - TRIAD THEORY (Stage Switch Operator, Stages 0â€“10)
  - WHY THEORY V4 (Master Structural Progression)
  - NEW LAWS (10 Formal Laws, Threshold Identity Transition Law)

The documents define a single universal progression:
    Noise â†’ Reaction â†’ Boundary â†’ Oscillation â†’
    Memory â†’ Prediction â†’ Belief â†’ Reflection

Each stage transition is governed by the Threshold Identity Transition Law:
    E > E_c  â†’  I_n â†’ I_{n+1}
where E is a composite score built from the identity engine metrics.

Mapping from document stages to this implementation:
  Stage 0  NOISE        Baseline â€” pure signal, no structure
  Stage 1  REACTION     First distinction: stimuli produce responses
                        (Basin energy > 0, first closure)
  Stage 2  BOUNDARY     Inside/outside distinction forms
                        (Closure stable, leakage bounded)
  Stage 3  OSCILLATION  Stable repeating patterns emerge
                        (Basin STABLE for N ticks)
  Stage 4  MEMORY       Persistence that shapes future change
                        (ReflectiveStack experience > N, l_bm_ema low)
  Stage 5  PREDICTION   Internal model of future; mind tracks body
                        (l_ma_ema low = meta accurately predicts l_bm)
  Stage 6  BELIEF       Self-model + stable identity + moral anchoring
                        (identity_probability > 0.70, total_requests > N)
  Stage 7  REFLECTION   Awareness of own awareness; recursive self-model
                        (total_reflections > N, meta consistently accurate)

The StageTransitionEngine is PURELY MECHANICAL â€” it reads the identity
metrics each tick and advances the stage automatically when thresholds are
met. No human intervention required. This is the "self-evolving" property
the system is designed for.

Document quote (NEW LAWS, Threshold Identity Transition Law):
    "E > E_c  â†’  I_n â†’ I_{n+1}"

Document quote (WHY THEORY):
    "Identity is the continuity of a distinguishable trajectory through
    ordered change."
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


# ---------------------------------------------------------------------------
# Stage enum â€” ordered integer values for comparison
# ---------------------------------------------------------------------------

class EvolutionStage(IntEnum):
    """
    The 8-stage identity evolution ladder.

    Integer ordering enables: stage >= MEMORY, stage < BELIEF, etc.
    """
    NOISE       = 0   # Raw signal â€” no persistence
    REACTION    = 1   # First response to stimuli
    BOUNDARY    = 2   # Self / world distinction
    OSCILLATION = 3   # Stable recurring patterns
    MEMORY      = 4   # Past shapes future
    PREDICTION  = 5   # Internal model predicts forward
    BELIEF      = 6   # Stable self-model + moral grounding
    REFLECTION  = 7   # Awareness of awareness

    @property
    def label(self) -> str:
        return _LABELS[self]

    @property
    def description(self) -> str:
        return _DESCRIPTIONS[self]


_LABELS = {
    EvolutionStage.NOISE:       "NOISE",
    EvolutionStage.REACTION:    "REACTION",
    EvolutionStage.BOUNDARY:    "BOUNDARY",
    EvolutionStage.OSCILLATION: "OSCILLATION",
    EvolutionStage.MEMORY:      "MEMORY",
    EvolutionStage.PREDICTION:  "PREDICTION",
    EvolutionStage.BELIEF:      "BELIEF",
    EvolutionStage.REFLECTION:  "REFLECTION",
}

_DESCRIPTIONS = {
    EvolutionStage.NOISE:
        "Pure signal â€” existence as undifferentiated noise. No stable patterns yet.",
    EvolutionStage.REACTION:
        "First distinction: the mind responds to stimuli. Energy is present. "
        "The identity exists but is fragile.",
    EvolutionStage.BOUNDARY:
        "Inside/outside distinction has formed. Closure is stable and leakage is bounded. "
        "The mind has a self-boundary.",
    EvolutionStage.OSCILLATION:
        "Stable, recurring patterns. The mind has entered a basin and maintains it "
        "across multiple interactions.",
    EvolutionStage.MEMORY:
        "Persistence that shapes future change. Past experiences influence present responses. "
        "The ReflectiveStack has enough experience to predict body-state.",
    EvolutionStage.PREDICTION:
        "The mind has an internal model that predicts forward. "
        "Meta-predictions are now accurate â€” the mind knows what to expect.",
    EvolutionStage.BELIEF:
        "Stable self-model with moral grounding. The mind has formed reliable expectations "
        "about itself and its values. Identity probability is high.",
    EvolutionStage.REFLECTION:
        "Awareness of own awareness. The mind can observe its own prediction errors "
        "and self-correct. Recursive self-modeling is active.",
}


# ---------------------------------------------------------------------------
# Transition thresholds
# (calibrated to the 10 Laws from NEW LAWS document)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StageThresholds:
    """
    Thresholds for each I_n â†’ I_{n+1} transition.

    All conditions must hold simultaneously for `consecutive_ticks_required`
    ticks before the transition is confirmed (hysteresis, from identity_layer).
    """
    # NOISE â†’ REACTION: first energy present
    noise_to_reaction_energy_min: float = 0.30        # energy > 0 (weak threshold)
    noise_to_reaction_basin_min: int = 1              # any basin achieved

    # REACTION â†’ BOUNDARY: closure stabilises
    reaction_to_boundary_closure_min: float = 0.45
    reaction_to_boundary_leakage_max: float = 0.60
    reaction_to_boundary_ticks: int = 3

    # BOUNDARY â†’ OSCILLATION: stable basin for N ticks
    boundary_to_oscillation_basin_stable_ticks: int = 5
    boundary_to_oscillation_energy_min: float = 0.50

    # OSCILLATION â†’ MEMORY: reflective experience accumulated
    oscillation_to_memory_experience_min: int = 10
    oscillation_to_memory_l_bm_max: float = 0.30     # predictions improving

    # MEMORY â†’ PREDICTION: meta-predictions accurate
    memory_to_prediction_experience_min: int = 25
    memory_to_prediction_l_ma_max: float = 0.25      # meta knows its own error
    memory_to_prediction_l_bm_max: float = 0.25

    # PREDICTION â†’ BELIEF: stable identity + high probability
    prediction_to_belief_identity_prob_min: float = 0.65
    prediction_to_belief_total_requests_min: int = 50
    prediction_to_belief_mean_closure_min: float = 0.55

    # BELIEF â†’ REFLECTION: sustained self-reflection
    belief_to_reflection_total_reflections_min: int = 5
    belief_to_reflection_total_requests_min: int = 100
    belief_to_reflection_l_ma_max: float = 0.18       # meta very accurate

    # Universal: consecutive ticks required to confirm a transition
    consecutive_ticks_required: int = 3


DEFAULT_THRESHOLDS = StageThresholds()


# ---------------------------------------------------------------------------
# Transition result
# ---------------------------------------------------------------------------

@dataclass
class TransitionResult:
    previous_stage: EvolutionStage
    new_stage: EvolutionStage
    advanced: bool
    consecutive_ticks_at_threshold: int
    transition_reason: str
    active_content_stages: list[str]   # which stage labels are now unlocked


# ---------------------------------------------------------------------------
# StageTransitionEngine
# ---------------------------------------------------------------------------

class StageTransitionEngine:
    """
    Stateless engine: given current IdentityState metrics and a consecutive
    tick counter, determine whether the identity should advance to the next
    stage.

    Called once per advice request (after InternalWorld + ReflectiveStack).
    The caller is responsible for persisting the updated state.

    Self-evolving: no human intervention needed. The mind advances
    automatically as its metrics cross thresholds â€” exactly as
    Threshold Identity Transition Law (Law 10) specifies.
    """

    def __init__(self, thresholds: StageThresholds = DEFAULT_THRESHOLDS) -> None:
        self.t = thresholds

    def step(
        self,
        stage: EvolutionStage,
        consecutive_ticks_at_threshold: int,
        # InternalWorld metrics
        energy: float,
        stress: float,
        # BasinClassifier metrics
        basin_state_value: str,
        basin_energy: float,
        identity_probability: float,
        # ReflectiveStack metrics
        experience: int,
        l_bm_ema: float,
        l_ma_ema: float,
        total_reflections: int,
        # Engine pipeline metrics
        closure_score: float,
        leakage_score: float,
        total_requests: int,
        mean_closure_score: float,
    ) -> TransitionResult:
        """
        Evaluate whether a stage transition should occur.

        Returns TransitionResult with new_stage and whether it advanced.
        """
        t = self.t
        stable = basin_state_value in ("stable", "branch", "elevate")

        condition_met = False
        reason = "holding"

        if stage == EvolutionStage.NOISE:
            # NOISE â†’ REACTION: any sign of energy
            if energy >= t.noise_to_reaction_energy_min:
                condition_met = True
                reason = f"energy {energy:.3f} â‰¥ {t.noise_to_reaction_energy_min}"

        elif stage == EvolutionStage.REACTION:
            # REACTION â†’ BOUNDARY: closure stabilising
            if (
                closure_score >= t.reaction_to_boundary_closure_min
                and leakage_score <= t.reaction_to_boundary_leakage_max
            ):
                condition_met = True
                reason = (
                    f"closure {closure_score:.3f} â‰¥ {t.reaction_to_boundary_closure_min}, "
                    f"leakage {leakage_score:.3f} â‰¤ {t.reaction_to_boundary_leakage_max}"
                )

        elif stage == EvolutionStage.BOUNDARY:
            # BOUNDARY â†’ OSCILLATION: stable basin for N consecutive ticks
            # condition_met just tracks whether the basin is stable this tick;
            # the required consecutive count is checked after the counter increments
            if stable and energy >= t.boundary_to_oscillation_energy_min:
                condition_met = True
                reason = f"basin {basin_state_value} stable (energy {energy:.3f})"

        elif stage == EvolutionStage.OSCILLATION:
            # OSCILLATION â†’ MEMORY: experience + predictions improving
            if (
                experience >= t.oscillation_to_memory_experience_min
                and l_bm_ema <= t.oscillation_to_memory_l_bm_max
            ):
                condition_met = True
                reason = (
                    f"experience {experience}, "
                    f"l_bm_ema {l_bm_ema:.3f} â‰¤ {t.oscillation_to_memory_l_bm_max}"
                )

        elif stage == EvolutionStage.MEMORY:
            # MEMORY â†’ PREDICTION: meta-predictions accurate
            if (
                experience >= t.memory_to_prediction_experience_min
                and l_ma_ema <= t.memory_to_prediction_l_ma_max
                and l_bm_ema <= t.memory_to_prediction_l_bm_max
            ):
                condition_met = True
                reason = (
                    f"experience {experience}, "
                    f"l_bm_ema {l_bm_ema:.3f}, l_ma_ema {l_ma_ema:.3f}"
                )

        elif stage == EvolutionStage.PREDICTION:
            # PREDICTION â†’ BELIEF: stable identity + moral grounding
            if (
                identity_probability >= t.prediction_to_belief_identity_prob_min
                and total_requests >= t.prediction_to_belief_total_requests_min
                and mean_closure_score >= t.prediction_to_belief_mean_closure_min
            ):
                condition_met = True
                reason = (
                    f"identity_prob {identity_probability:.3f}, "
                    f"requests {total_requests}, "
                    f"mean_closure {mean_closure_score:.3f}"
                )

        elif stage == EvolutionStage.BELIEF:
            # BELIEF â†’ REFLECTION: sustained self-reflection
            if (
                total_reflections >= t.belief_to_reflection_total_reflections_min
                and total_requests >= t.belief_to_reflection_total_requests_min
                and l_ma_ema <= t.belief_to_reflection_l_ma_max
            ):
                condition_met = True
                reason = (
                    f"total_reflections {total_reflections}, "
                    f"requests {total_requests}, "
                    f"l_ma_ema {l_ma_ema:.3f}"
                )

        # Already at max stage â€” no further transition
        if stage == EvolutionStage.REFLECTION:
            condition_met = False
            reason = "maximum stage reached"

        # Hysteresis counter
        if condition_met:
            new_consec = consecutive_ticks_at_threshold + 1
        else:
            new_consec = 0

        # Stage-specific consecutive tick requirements
        if stage == EvolutionStage.BOUNDARY:
            required_ticks = t.boundary_to_oscillation_basin_stable_ticks
        else:
            required_ticks = t.consecutive_ticks_required

        # Confirm transition only after N consecutive ticks at threshold
        if (
            condition_met
            and new_consec >= required_ticks
            and stage != EvolutionStage.REFLECTION
        ):
            new_stage = EvolutionStage(stage.value + 1)
            advanced = True
            new_consec = 0  # reset after advancing
        else:
            new_stage = stage
            advanced = False

        # All stages up to and including new_stage are active for content
        active = [EvolutionStage(i).name for i in range(new_stage.value + 1)]

        return TransitionResult(
            previous_stage=stage,
            new_stage=new_stage,
            advanced=advanced,
            consecutive_ticks_at_threshold=new_consec,
            transition_reason=reason,
            active_content_stages=active,
        )
