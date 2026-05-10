"""
MindAI Layer objects — composable pipeline units.

Each Layer follows the existence_lab interface exactly:
  - name: str
  - on_reset(ctx): called once per pipeline run (optional setup)
  - on_step(ctx):  called once per tick to do its work

State NEVER lives in the Layer — only in ctx.identity.* and ctx.cache.*.
Layers NEVER call each other directly — they communicate only through ctx.

Layer execution order (identity_engine.run_pipeline):
  0. SensoryLayer        — multi-channel integration, bias UserState
  1. ResidualRealityLayer — residual novelty + reality-check kernel
  2. MoralLayer          — moral kernel, wave moral amplitude
  3. InternalWorldLayer  — energy/stress dynamics
  4. ReflectionLayer     — body-mind-meta prediction + losses
  5. ClosureStrainLayer  — closure/leakage/lag + compatibility + strain
  6. BasinStageLayer     — basin classification + stage transition
  7. WaveObserveLayer    — pattern observer, reflection write-back, attention, habitat
  8. DecisionLayer       — stability band + inner voice + candidate selection
"""

from .base import MindLayer
from .sensory_layer import SensoryLayer
from .residual_reality_layer import ResidualRealityLayer
from .moral_layer import MoralLayer
from .internal_world_layer import InternalWorldLayer
from .reflection_layer import ReflectionLayer
from .closure_strain_layer import ClosureStrainLayer
from .basin_stage_layer import BasinStageLayer
from .wave_observe_layer import WaveObserveLayer
from .subconscious_layer import SubconsciousLayer
from .global_coupler_layer import GlobalCouplerLayer
from .oscillation_layer import OscillationLayer
from .belief_layer import BeliefLayer
from .identity_gravity_layer import IdentityGravityLayer
from .social_field_layer import SocialFieldLayer
from .conscious_layer import ConsciousLayer
from .decision_layer import DecisionLayer
from .adaptive_law_layer import AdaptiveLawLayer
from .convergence_cognition_layer import ConvergenceCognitionLayer
from .generational_cycle_layer import GenerationalCycleLayer
from .wisdom_transfer_layer import WisdomTransferLayer
from .seed_enrichment_layer import SeedEnrichmentLayer
from .life_event_layer import LifeEventLayer
from .world_input_layer import WorldInputLayer

__all__ = [
    "MindLayer",
    "SensoryLayer",
    "ResidualRealityLayer",
    "MoralLayer",
    "InternalWorldLayer",
    "ReflectionLayer",
    "ClosureStrainLayer",
    "BasinStageLayer",
    "WaveObserveLayer",
    "SubconsciousLayer",
    "GlobalCouplerLayer",
    "OscillationLayer",
    "BeliefLayer",
    "IdentityGravityLayer",
    "SocialFieldLayer",
    "ConsciousLayer",
    "DecisionLayer",
    "AdaptiveLawLayer",
    "ConvergenceCognitionLayer",
    "GenerationalCycleLayer",
    "WisdomTransferLayer",
    "SeedEnrichmentLayer",
    "LifeEventLayer",
    "WorldInputLayer",
]
