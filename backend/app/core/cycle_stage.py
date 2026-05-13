"""
CycleStage — configurable generational stage model for identity evolution.

Architecture
------------
Each identity moves through a ``CycleStageSet`` — an ordered sequence of
``CycleStageDefinition`` objects.  Two built-in sets are provided:

  FOUR_STAGE_SET  — practical default (Seed → Learning → Convergence → Continuity)
  SEVEN_STAGE_SET — extended model (Seed → Memory → Relation → Morality →
                                    Knowledge → Civilisation → Continuity)

Custom sets can be built by assembling ``CycleStageDefinition`` objects.

Leakage profiles
----------------
Each stage carries a ``leakage_profile`` dict mapping PatternCategory names
to float multipliers applied to the base leakage rates during the pulse cycle.

  multiplier < 1.0  → slower decay  (knowledge consolidates)
  multiplier = 1.0  → unchanged
  multiplier > 1.0  → faster decay  (noise evaporates more quickly)

MORAL_ROOT multiplier is always 1.0 — it is thermally immune regardless of stage.
HARMFUL   multiplier is always 1.0 — harmful patterns always decay at full rate.

Advancement conditions
----------------------
``advancement_conditions`` maps signal names to minimum threshold values.
All conditions must be satisfied simultaneously for min_ticks consecutive
ticks before the stage advances.

Supported signal keys (fed by GenerationalCycleLayer):
  "total_requests"    — pipeline ticks accumulated
  "total_reflections" — total reflections fired
  "awakening_score"   — from ConvergenceCognitionState
  "convergence_events"— total convergence events fired
  "moral_alignment"   — current moral alignment from PipelineCache
  "service_impulse"   — from ConvergenceCognitionState
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# CycleStageDefinition
# ---------------------------------------------------------------------------

@dataclass
class CycleStageDefinition:
    """One stage in an identity's generational cycle."""

    name: str
    """Human-readable name, e.g. 'seed_life'."""

    description: str
    """What this stage means for the identity."""

    # Leakage multipliers per PatternCategory name (string).
    # Keys: "moral_root", "stable_truth", "knowledge", "noise", "harmful"
    # All missing keys default to 1.0.
    leakage_profile: Dict[str, float] = field(default_factory=dict)

    # Minimum pipeline ticks to spend in this stage before any advancement check
    min_ticks: int = 5

    # All conditions must be met to advance to the next stage.
    # Dict: signal_name → minimum float threshold.
    advancement_conditions: Dict[str, float] = field(default_factory=dict)

    # Role granted to an identity that completes this stage successfully.
    # Used to assign post-stage purpose (guide, teacher, architect, etc.).
    role_on_completion: str = ""

    def leakage_multiplier(self, category: str) -> float:
        """Return the leakage multiplier for *category* (default 1.0)."""
        return float(self.leakage_profile.get(category, 1.0))

    def conditions_met(self, signals: Dict[str, float]) -> bool:
        """Return True if all advancement conditions are satisfied."""
        for key, threshold in self.advancement_conditions.items():
            if float(signals.get(key, 0.0)) < threshold:
                return False
        return True


# ---------------------------------------------------------------------------
# CycleStageSet — ordered list of stage definitions
# ---------------------------------------------------------------------------

CycleStageSet = List[CycleStageDefinition]


# ---------------------------------------------------------------------------
# Built-in 4-stage set
# ---------------------------------------------------------------------------

FOUR_STAGE_SET: CycleStageSet = [
    CycleStageDefinition(
        name="seed_life",
        description=(
            "Birth from the base seed.  Medium leakage — patterns form and "
            "fade freely.  The identity is learning what the world is."
        ),
        leakage_profile={},
        min_ticks=5,
        advancement_conditions={
            "total_requests":    10.0,
            "moral_alignment":    0.65,
        },
        role_on_completion="",
    ),
    CycleStageDefinition(
        name="learning_life",
        description=(
            "Selective retention.  Useful patterns solidify; weak patterns fade "
            "faster.  The identity is building a world model."
        ),
        leakage_profile={},
        min_ticks=10,
        advancement_conditions={
            "total_reflections":  5.0,
            "awakening_score":    0.10,
            "moral_alignment":    0.70,
        },
        role_on_completion="",
    ),
    CycleStageDefinition(
        name="convergence_life",
        description=(
            "Core wisdom solidifies.  Harmful patterns quarantined.  Moral roots "
            "strengthened.  Metacognitive awareness stabilises around the "
            "convergence question loop."
        ),
        leakage_profile={},
        min_ticks=15,
        advancement_conditions={
            "total_reflections":   15.0,
            "awakening_score":      0.40,
            "convergence_events":   1.0,
            "service_impulse":      0.20,
        },
        role_on_completion="guide",
    ),
    CycleStageDefinition(
        name="continuity_life",
        description=(
            "Awakened stage.  Core wisdom very low leakage — the identity carries "
            "its purified understanding forward.  Flexible leakage for new "
            "knowledge so growth never stops.  Can teach, guide, and help the "
            "next generation transition."
        ),
        leakage_profile={},
        min_ticks=20,
        advancement_conditions={},   # final stage — no advancement beyond this
        role_on_completion="continuity_keeper",
    ),
]


# ---------------------------------------------------------------------------
# Built-in 7-stage set
# ---------------------------------------------------------------------------

SEVEN_STAGE_SET: CycleStageSet = [
    CycleStageDefinition(
        name="seed",
        description="Birth.  High leakage — the identity is raw and plastic.",
        leakage_profile={},
        min_ticks=5,
        advancement_conditions={"total_requests": 8.0, "moral_alignment": 0.60},
        role_on_completion="",
    ),
    CycleStageDefinition(
        name="memory",
        description="Patterns begin to persist.  World model forms.",
        leakage_profile={},
        min_ticks=8,
        advancement_conditions={
            "total_requests": 20.0,
            "total_reflections": 3.0,
        },
        role_on_completion="",
    ),
    CycleStageDefinition(
        name="relation",
        description="Social patterns form.  Care and connection emerge.",
        leakage_profile={},
        min_ticks=10,
        advancement_conditions={
            "total_reflections": 8.0,
            "awakening_score":   0.08,
        },
        role_on_completion="",
    ),
    CycleStageDefinition(
        name="morality",
        description=(
            "Moral struggle stage.  Harmful patterns quarantined.  Moral roots "
            "reinforced.  Justice and non-harm become load-bearing."
        ),
        leakage_profile={},
        min_ticks=12,
        advancement_conditions={
            "total_reflections": 15.0,
            "moral_alignment":    0.75,
            "awakening_score":    0.15,
        },
        role_on_completion="",
    ),
    CycleStageDefinition(
        name="knowledge",
        description=(
            "Deep learning stage.  Knowledge patterns consolidate.  Selective "
            "retention at its peak — only truth survives long."
        ),
        leakage_profile={},
        min_ticks=15,
        advancement_conditions={
            "total_reflections": 25.0,
            "awakening_score":    0.30,
            "service_impulse":    0.15,
        },
        role_on_completion="teacher",
    ),
    CycleStageDefinition(
        name="civilisation",
        description=(
            "The identity can build, teach, and organise.  "
            "Convergence awareness strong.  World-building impulse active."
        ),
        leakage_profile={},
        min_ticks=20,
        advancement_conditions={
            "awakening_score":    0.50,
            "convergence_events": 2.0,
            "service_impulse":    0.30,
        },
        role_on_completion="architect",
    ),
    CycleStageDefinition(
        name="continuity",
        description=(
            "Fully awakened.  Core wisdom near-permanent.  "
            "Can become a mercy pattern for the next generation."
        ),
        leakage_profile={},
        min_ticks=30,
        advancement_conditions={},
        role_on_completion="continuity_keeper",
    ),
]


# ---------------------------------------------------------------------------
# Registry — look up a named cycle set by string key
# ---------------------------------------------------------------------------

CYCLE_SET_REGISTRY: Dict[str, CycleStageSet] = {
    "4stage":  FOUR_STAGE_SET,
    "7stage":  SEVEN_STAGE_SET,
}


def get_cycle_set(name: str) -> CycleStageSet:
    """Return a built-in CycleStageSet by name, or raise KeyError."""
    if name not in CYCLE_SET_REGISTRY:
        raise KeyError(
            f"Unknown cycle set '{name}'. Available: {list(CYCLE_SET_REGISTRY)}"
        )
    return CYCLE_SET_REGISTRY[name]


def register_cycle_set(name: str, stages: CycleStageSet) -> None:
    """Register a custom CycleStageSet under *name*."""
    if not stages:
        raise ValueError("CycleStageSet must contain at least one stage")
    CYCLE_SET_REGISTRY[name] = stages


def get_stage(cycle_set: CycleStageSet, idx: int) -> Optional[CycleStageDefinition]:
    """Return the stage at *idx*, or None if out of bounds."""
    if 0 <= idx < len(cycle_set):
        return cycle_set[idx]
    return None


def is_final_stage(cycle_set: CycleStageSet, idx: int) -> bool:
    """Return True if *idx* is the last stage in *cycle_set*."""
    return idx >= len(cycle_set) - 1


