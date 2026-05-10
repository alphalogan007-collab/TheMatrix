"""
proto_codec.py — Encode/decode IdentityState ↔ protobuf binary.

This module is the ONLY place that touches the generated _pb2 stubs.
`identity_store.py` calls:

    encode(state: IdentityState) -> bytes
    decode(data: bytes, user_id: str) -> IdentityState

Migration shim
--------------
During the transition period Redis may still hold old JSON blobs.
`smart_decode(data, user_id)` auto-detects the format:
  • Starts with b'{' → JSON path (via old identity_store.deserialise)
  • Otherwise        → proto path

This lets us roll out without flushing Redis.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.identity_context import IdentityState as _ISType

logger = logging.getLogger(__name__)

# ── lazy import helpers ───────────────────────────────────────────────────────

def _pb2():
    from app.core.proto import identity_state_pb2
    return identity_state_pb2


# ── internal field converters ─────────────────────────────────────────────────

def _iw_to_pb(iw, pb_iw):
    pb_iw.energy            = iw.energy
    pb_iw.stress            = iw.stress
    pb_iw.in_basin          = iw.in_basin
    pb_iw.worldness         = iw.worldness
    pb_iw.stability         = iw.stability
    pb_iw.ticks             = iw.ticks
    pb_iw.last_closure_bias = iw.last_closure_bias
    pb_iw.last_leak_bias    = iw.last_leak_bias
    cw = iw.channel_weights
    pb_iw.channel_weights.closure = cw.get("closure", 1.0) if isinstance(cw, dict) else getattr(cw, "closure", 1.0)
    pb_iw.channel_weights.leak    = cw.get("leak",    1.0) if isinstance(cw, dict) else getattr(cw, "leak",    1.0)
    pb_iw.channel_weights.action  = cw.get("action",  1.0) if isinstance(cw, dict) else getattr(cw, "action",  1.0)


def _rs_to_pb(rs, pb_rs):
    pb_rs.meta_pred             = rs.meta_pred
    pb_rs.l_bm                  = rs.l_bm
    pb_rs.l_ma                  = rs.l_ma
    pb_rs.l_bm_ema              = rs.l_bm_ema
    pb_rs.l_ma_ema              = rs.l_ma_ema
    pb_rs.consecutive_meta_over = rs.consecutive_meta_over
    pb_rs.reflection_triggered  = rs.reflection_triggered
    pb_rs.total_reflections     = rs.total_reflections
    pb_rs.mind_pred[:]          = [float(v) for v in rs.mind_pred]
    extra = getattr(rs, "extra_losses", [])
    pb_rs.extra_losses[:]       = [float(v) for v in extra]


def _ms_to_pb(ms, pb_ms):
    pb_ms.moral_amplitude           = ms.moral_amplitude
    pb_ms.alignment_ema             = ms.alignment_ema
    pb_ms.concern_streak            = ms.concern_streak
    pb_ms.last_harmful_tick         = ms.last_harmful_tick
    pb_ms.correction_count          = ms.correction_count
    pb_ms.harmful_pattern_exposures = ms.harmful_pattern_exposures
    pb_ms.last_tick                 = ms.last_tick


def _at_to_pb(at, pb_at):
    pb_at.focused_pattern_ids[:] = list(at.focused_pattern_ids)
    pb_at.focus_strength         = at.focus_strength
    pb_at.saccade_count          = at.saccade_count
    pb_at.topic_continuity       = at.topic_continuity
    pb_at.last_tick              = at.last_tick


def _hab_to_pb(h, pb_h):
    pb_h.pos_x         = h.pos_x
    pb_h.pos_y         = h.pos_y
    pb_h.nutrients[:]  = [float(v) for v in h.nutrients]
    for e in getattr(h, "social_entities", []):
        pb_e = pb_h.social_entities.add()
        pb_e.peer_id            = e.peer_id
        pb_e.peer_mass          = e.peer_mass
        pb_e.resonance_vec[:]   = [float(v) for v in e.resonance_vec]
        pb_e.influence_score    = e.influence_score
        pb_e.last_pos_x         = e.last_pos_x
        pb_e.last_pos_y         = e.last_pos_y
        pb_e.last_contact_tick  = e.last_contact_tick
        pb_e.contact_count      = e.contact_count
        pb_e.is_flagged         = e.is_flagged


def _coupler_to_pb(c, pb_c):
    for pid, phase in c.pattern_phases.items():
        pb_c.pattern_phases[pid] = float(phase)
    pb_c.global_synchrony          = c.global_synchrony
    pb_c.awareness_emerged         = c.awareness_emerged
    pb_c.awareness_gate_streak     = c.awareness_gate_streak
    pb_c.identity_continuity       = c.identity_continuity
    pb_c.awareness_continuity      = c.awareness_continuity
    pb_c.self_awareness_continuity = c.self_awareness_continuity
    pb_c.last_tick                 = c.last_tick


def _belief_state_to_pb(bs, pb_bs, pb2):
    for b in bs.beliefs:
        pb_b = pb_bs.beliefs.add()
        pb_b.belief_id        = b.belief_id
        pb_b.pattern_id       = b.pattern_id
        pb_b.label            = b.label
        pb_b.amplitude        = b.amplitude
        pb_b.center[:]        = [float(v) for v in b.center]
        pb_b.formed_tick      = b.formed_tick
        pb_b.last_tick        = b.last_tick
        pb_b.is_contradicted  = b.is_contradicted
    for pid, tick in bs.pattern_ticks.items():
        pb_bs.pattern_ticks[pid] = int(tick)
    pb_bs.contradiction_score    = bs.contradiction_score
    pb_bs.last_contradiction_tick = bs.last_contradiction_tick
    pb_bs.total_beliefs_formed   = bs.total_beliefs_formed
    pb_bs.last_tick              = bs.last_tick


def _raw_memory_to_pb(rm, pb_rm, pb2):
    for t in rm.traces:
        pb_t = pb_rm.traces.add()
        pb_t.trace_id        = t.trace_id
        pb_t.source          = t.source
        pb_t.content_hash    = t.content_hash
        pb_t.activation      = t.activation
        pb_t.state           = t.state.value if hasattr(t.state, "value") else str(t.state)
        pb_t.moral_risk      = t.moral_risk
        pb_t.confidence      = t.confidence
        pb_t.emotional_charge = t.emotional_charge
        pb_t.formed_tick     = t.formed_tick
        pb_t.last_tick       = t.last_tick
        pb_t.leakage_rate    = t.leakage_rate
        pb_t.pattern_ids[:]  = list(t.pattern_ids)
        pb_t.is_quarantined  = t.is_quarantined
    pb_rm.total_traces_formed = rm.total_traces_formed
    pb_rm.last_tick           = rm.last_tick
    pb_rm.max_traces          = rm.max_traces


def _thought_to_pb(t, pb_t):
    pb_t.thought_id             = t.thought_id
    pb_t.source_trace_ids[:]   = list(t.source_trace_ids)
    pb_t.source_pattern_ids[:] = list(t.source_pattern_ids)
    pb_t.activation_strength   = t.activation_strength
    pb_t.moral_risk            = t.moral_risk
    pb_t.novelty               = t.novelty
    pb_t.relevance             = t.relevance
    pb_t.unresolved_score      = t.unresolved_score
    pb_t.emotional_charge      = t.emotional_charge
    pb_t.suggested_question    = t.suggested_question or ""
    pb_t.formed_tick           = t.formed_tick
    pb_t.leakage_rate          = t.leakage_rate


def _cw_to_pb(cw, pb_cw):
    for t in cw.active_thoughts:
        _thought_to_pb(t, pb_cw.active_thoughts.add())
    pb_cw.max_active              = cw.max_active
    pb_cw.last_tick               = cw.last_tick
    pb_cw.cycles_without_reflection = cw.cycles_without_reflection


def _osc_to_pb(o, pb_o):
    pb_o.phase                = o.phase
    pb_o.natural_frequency    = o.natural_frequency
    pb_o.pulse_amplitude      = o.pulse_amplitude
    pb_o.inner_pressure       = o.inner_pressure
    pb_o.outer_pressure       = o.outer_pressure
    pb_o.boundary_flux        = o.boundary_flux
    pb_o.entrainment_strength = o.entrainment_strength
    pb_o.emission_strength    = o.emission_strength
    pb_o.reception_strength   = o.reception_strength
    pb_o.last_tick            = o.last_tick
    pb_o.total_cycles         = int(getattr(o, "total_cycles", 0))


def _wp_to_pb(w, pb_w):
    pb_w.pattern_id       = w.get("pattern_id", "")
    pb_w.center[:]        = [float(v) for v in w.get("center", [])]
    pb_w.amplitude        = float(w.get("amplitude", 0.5))
    pb_w.width            = float(w.get("width", 0.1))
    pb_w.decay_rate       = float(w.get("decay_rate", 0.002))
    pb_w.last_tick        = int(w.get("last_tick", 0))
    pb_w.last_temperature = float(w.get("last_temperature", 0.0))
    pb_w.mean_closure     = float(w.get("mean_closure", 0.0))
    pb_w.observation_count = int(w.get("observation_count", 1))
    pb_w.guidance_mode    = str(w.get("guidance_mode", "open"))
    pb_w.evolution_stage  = str(w.get("evolution_stage", "NOISE"))
    pb_w.category         = str(w.get("category", "knowledge"))
    pb_w.is_promoted      = bool(w.get("is_promoted", False))


# ── Public API ────────────────────────────────────────────────────────────────

def encode(state: "_ISType") -> bytes:
    """Serialise IdentityState → protobuf bytes."""
    pb2 = _pb2()
    pb  = pb2.IdentityState()

    pb.user_id              = state.user_id
    pb.blueprint_version_id = state.blueprint_version_id
    pb.blueprint_checksum   = state.blueprint_checksum

    _iw_to_pb(state.internal_world,  pb.internal_world)
    _rs_to_pb(state.reflective_stack, pb.reflective_stack)

    pb.basin_state             = state.basin_state.value if hasattr(state.basin_state, "value") else str(state.basin_state)
    pb.identity_probability    = state.identity_probability
    pb.evolution_stage         = state.evolution_stage.name if hasattr(state.evolution_stage, "name") else str(state.evolution_stage)
    pb.stage_consecutive_ticks = state.stage_consecutive_ticks
    pb.stage_history[:]        = list(state.stage_history)
    pb.total_requests          = state.total_requests
    pb.total_reflections       = state.total_reflections
    pb.mean_closure_score      = state.mean_closure_score
    pb.mean_strain_score       = state.mean_strain_score
    pb.closure_history[:]      = [float(v) for v in state.closure_history]

    for ch, vals in state.channel_models.items():
        pb.channel_models[ch].values[:] = [float(v) for v in vals]

    for wp in state.wave_patterns:
        _wp_to_pb(wp, pb.wave_patterns.add())

    _ms_to_pb(state.moral_state,    pb.moral_state)
    _at_to_pb(state.attention_state, pb.attention_state)
    _hab_to_pb(state.habitat_state, pb.habitat_state)
    _coupler_to_pb(state.coupler_state, pb.coupler_state)
    _belief_state_to_pb(state.belief_state, pb.belief_state, pb2)
    _raw_memory_to_pb(state.raw_memory, pb.raw_memory, pb2)

    for t in state.thought_queue:
        _thought_to_pb(t, pb.thought_queue.add())

    _cw_to_pb(state.conscious_workspace, pb.conscious_workspace)
    _osc_to_pb(state.oscillation_state, pb.oscillation_state)

    for k, v in state.params.items():
        pb.params[k] = float(v)

    return pb.SerializeToString()


def decode(data: bytes, user_id: str) -> "_ISType":
    """Deserialise protobuf bytes → IdentityState."""
    from app.core.identity_store import _deserialise_from_dict

    pb2 = _pb2()
    pb  = pb2.IdentityState()
    pb.ParseFromString(data)

    # Convert pb back to the plain-dict format _deserialise_from_dict already handles
    d: dict = {}
    d["user_id"]              = pb.user_id or user_id
    d["blueprint_version_id"] = pb.blueprint_version_id
    d["blueprint_checksum"]   = pb.blueprint_checksum

    d["internal_world"] = {
        "energy":            pb.internal_world.energy,
        "stress":            pb.internal_world.stress,
        "channel_weights": {
            "closure": pb.internal_world.channel_weights.closure,
            "leak":    pb.internal_world.channel_weights.leak,
            "action":  pb.internal_world.channel_weights.action,
        },
        "in_basin":          pb.internal_world.in_basin,
        "worldness":         pb.internal_world.worldness,
        "stability":         pb.internal_world.stability,
        "ticks":             pb.internal_world.ticks,
        "last_closure_bias": pb.internal_world.last_closure_bias,
        "last_leak_bias":    pb.internal_world.last_leak_bias,
    }

    d["reflective_stack"] = {
        "mind_pred":             list(pb.reflective_stack.mind_pred),
        "meta_pred":             pb.reflective_stack.meta_pred,
        "l_bm":                  pb.reflective_stack.l_bm,
        "l_ma":                  pb.reflective_stack.l_ma,
        "l_bm_ema":              pb.reflective_stack.l_bm_ema,
        "l_ma_ema":              pb.reflective_stack.l_ma_ema,
        "consecutive_meta_over": pb.reflective_stack.consecutive_meta_over,
        "reflection_triggered":  pb.reflective_stack.reflection_triggered,
        "total_reflections":     pb.reflective_stack.total_reflections,
        "extra_losses":          list(pb.reflective_stack.extra_losses),
        "experience":            0,
    }

    d["basin_state"]             = pb.basin_state
    d["identity_probability"]    = pb.identity_probability
    d["evolution_stage"]         = pb.evolution_stage
    d["stage_consecutive_ticks"] = pb.stage_consecutive_ticks
    d["stage_history"]           = list(pb.stage_history)
    d["total_requests"]          = pb.total_requests
    d["total_reflections"]       = pb.total_reflections
    d["mean_closure_score"]      = pb.mean_closure_score
    d["mean_strain_score"]       = pb.mean_strain_score
    d["closure_history"]         = list(pb.closure_history)
    d["channel_models"]          = {ch: list(fl.values) for ch, fl in pb.channel_models.items()}

    d["wave_patterns"] = [
        {
            "pattern_id":       w.pattern_id,
            "center":           list(w.center),
            "amplitude":        w.amplitude,
            "width":            w.width,
            "decay_rate":       w.decay_rate,
            "last_tick":        w.last_tick,
            "last_temperature": w.last_temperature,
            "mean_closure":     w.mean_closure,
            "observation_count": w.observation_count,
            "guidance_mode":    w.guidance_mode,
            "evolution_stage":  w.evolution_stage,
            "category":         w.category,
            "is_promoted":      w.is_promoted,
        }
        for w in pb.wave_patterns
    ]

    d["moral_state"] = {
        "moral_amplitude":           pb.moral_state.moral_amplitude,
        "alignment_ema":             pb.moral_state.alignment_ema,
        "concern_streak":            pb.moral_state.concern_streak,
        "last_harmful_tick":         pb.moral_state.last_harmful_tick,
        "correction_count":          pb.moral_state.correction_count,
        "harmful_pattern_exposures": pb.moral_state.harmful_pattern_exposures,
        "last_tick":                 pb.moral_state.last_tick,
    }

    d["attention_state"] = {
        "focused_pattern_ids": list(pb.attention_state.focused_pattern_ids),
        "focus_strength":      pb.attention_state.focus_strength,
        "saccade_count":       pb.attention_state.saccade_count,
        "topic_continuity":    pb.attention_state.topic_continuity,
        "last_tick":           pb.attention_state.last_tick,
    }

    d["habitat_state"] = {
        "pos_x":     pb.habitat_state.pos_x,
        "pos_y":     pb.habitat_state.pos_y,
        "nutrients": list(pb.habitat_state.nutrients),
        "social_entities": [
            {
                "peer_id":           e.peer_id,
                "peer_mass":         e.peer_mass,
                "resonance_vec":     list(e.resonance_vec),
                "influence_score":   e.influence_score,
                "last_pos_x":        e.last_pos_x,
                "last_pos_y":        e.last_pos_y,
                "last_contact_tick": e.last_contact_tick,
                "contact_count":     e.contact_count,
                "is_flagged":        e.is_flagged,
            }
            for e in pb.habitat_state.social_entities
        ],
    }

    d["coupler_state"] = {
        "pattern_phases":            dict(pb.coupler_state.pattern_phases),
        "global_synchrony":          pb.coupler_state.global_synchrony,
        "awareness_emerged":         pb.coupler_state.awareness_emerged,
        "awareness_gate_streak":     pb.coupler_state.awareness_gate_streak,
        "identity_continuity":       pb.coupler_state.identity_continuity,
        "awareness_continuity":      pb.coupler_state.awareness_continuity,
        "self_awareness_continuity": pb.coupler_state.self_awareness_continuity,
        "last_tick":                 pb.coupler_state.last_tick,
    }

    d["belief_state"] = {
        "beliefs": [
            {
                "belief_id":       b.belief_id,
                "pattern_id":      b.pattern_id,
                "label":           b.label,
                "amplitude":       b.amplitude,
                "center":          list(b.center),
                "formed_tick":     b.formed_tick,
                "last_tick":       b.last_tick,
                "is_contradicted": b.is_contradicted,
            }
            for b in pb.belief_state.beliefs
        ],
        "pattern_ticks":          dict(pb.belief_state.pattern_ticks),
        "contradiction_score":    pb.belief_state.contradiction_score,
        "last_contradiction_tick": pb.belief_state.last_contradiction_tick,
        "total_beliefs_formed":   pb.belief_state.total_beliefs_formed,
        "last_tick":              pb.belief_state.last_tick,
    }

    d["raw_memory"] = {
        "traces": [
            {
                "trace_id":        t.trace_id,
                "source":          t.source,
                "content_hash":    t.content_hash,
                "activation":      t.activation,
                "state":           t.state,
                "moral_risk":      t.moral_risk,
                "confidence":      t.confidence,
                "emotional_charge": t.emotional_charge,
                "formed_tick":     t.formed_tick,
                "last_tick":       t.last_tick,
                "leakage_rate":    t.leakage_rate,
                "pattern_ids":     list(t.pattern_ids),
                "is_quarantined":  t.is_quarantined,
            }
            for t in pb.raw_memory.traces
        ],
        "total_traces_formed": pb.raw_memory.total_traces_formed,
        "last_tick":           pb.raw_memory.last_tick,
        "max_traces":          pb.raw_memory.max_traces,
    }

    def _tc_to_dict(t):
        return {
            "thought_id":          t.thought_id,
            "source_trace_ids":    list(t.source_trace_ids),
            "source_pattern_ids":  list(t.source_pattern_ids),
            "activation_strength": t.activation_strength,
            "moral_risk":          t.moral_risk,
            "novelty":             t.novelty,
            "relevance":           t.relevance,
            "unresolved_score":    t.unresolved_score,
            "emotional_charge":    t.emotional_charge,
            "suggested_question":  t.suggested_question or None,
            "formed_tick":         t.formed_tick,
            "leakage_rate":        t.leakage_rate,
        }

    d["thought_queue"] = [_tc_to_dict(t) for t in pb.thought_queue]

    d["conscious_workspace"] = {
        "active_thoughts":         [_tc_to_dict(t) for t in pb.conscious_workspace.active_thoughts],
        "max_active":              pb.conscious_workspace.max_active,
        "last_tick":               pb.conscious_workspace.last_tick,
        "cycles_without_reflection": pb.conscious_workspace.cycles_without_reflection,
    }

    d["oscillation_state"] = {
        "phase":                pb.oscillation_state.phase,
        "natural_frequency":    pb.oscillation_state.natural_frequency,
        "pulse_amplitude":      pb.oscillation_state.pulse_amplitude,
        "inner_pressure":       pb.oscillation_state.inner_pressure,
        "outer_pressure":       pb.oscillation_state.outer_pressure,
        "boundary_flux":        pb.oscillation_state.boundary_flux,
        "entrainment_strength": pb.oscillation_state.entrainment_strength,
        "emission_strength":    pb.oscillation_state.emission_strength,
        "reception_strength":   pb.oscillation_state.reception_strength,
        "last_tick":            pb.oscillation_state.last_tick,
        "total_cycles":         pb.oscillation_state.total_cycles,
    }

    d["params"] = dict(pb.params)

    return _deserialise_from_dict(d, user_id)


def smart_decode(data: bytes, user_id: str) -> "_ISType":
    """
    Auto-detect JSON vs proto binary and route accordingly.
    Needed during the migration window when Redis may hold either format.
    """
    if data[:1] == b"{":
        # Legacy JSON path
        from app.core.identity_store import deserialise as _json_deserialise
        return _json_deserialise(data.decode("utf-8"), user_id)
    return decode(data, user_id)
