"""
SocialFieldLayer — Habitat Phase 2: Social Gravity

Pipeline slot: after IdentityGravityLayer, before ConsciousLayer

Every identity in the habitat exerts a gravitational pull on this identity's
wave field, governed by the same G_ij formula used in identity_gravity:

    G_social_j = (M_i * M_j * R_ij * C_ij) / (D_spatial_j + ε)

Where:
  M_i           = this identity's mass (from ctx.cache.extra["identity_mass"])
  M_j           = peer's mass (SocialEntity.peer_mass)
  R_ij          = cosine similarity between identity centroid and peer resonance_vec
  C_ij          = 1.0 - contradiction_score  (alignment factor)
  D_spatial_j   = Euclidean distance between habitat positions / GRID_SIZE
  ε             = 0.01

Effects
-------
• social_pull vector: weighted average of aligned peer resonance vectors.
  Gently nudges the identity's belief centroid (via OscillationLayer outer_pressure boost).
• social_pressure: scalar added to ctx.identity.oscillation_state.outer_pressure.
• Flagged peers (is_flagged=True) contribute negative influence.
• Publishes to ctx.cache.extra:
    social_pull          (List[float])
    social_pressure      (float)
    dominant_peer_id     (str)
    social_peer_count    (int)
    aligned_peer_count   (int)
    repelled_peer_count  (int)
"""

from __future__ import annotations

import logging
import math
from typing import List

from app.core.layers.base import MindLayer
from app.core.identity_context import IdentityContext
from app.core.identity_context import getp

logger = logging.getLogger(__name__)

_EPSILON = 0.01
_TWO_PI  = 2 * math.pi

# Max number of peers to consider per tick (performance cap)
_MAX_PEERS = 20


def _cosine(a: List[float], b: List[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot  = sum(x * y for x, y in zip(a, b))
    na   = math.sqrt(sum(x * x for x in a))
    nb   = math.sqrt(sum(y * y for y in b))
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return max(-1.0, min(1.0, dot / (na * nb)))


class SocialFieldLayer(MindLayer):
    name = "social_field"

    def on_step(self, ctx: IdentityContext) -> None:
        try:
            self._run(ctx)
        except Exception as err:
            logger.warning("SocialFieldLayer error (non-fatal): %s", err)

    def _run(self, ctx: IdentityContext) -> None:
        identity = ctx.identity
        habitat  = identity.habitat_state
        peers    = habitat.social_entities

        if not peers:
            ctx.cache.extra.update({
                "social_pull":         [],
                "social_pressure":     0.0,
                "dominant_peer_id":    "",
                "social_peer_count":   0,
                "aligned_peer_count":  0,
                "repelled_peer_count": 0,
            })
            return

        # -- Tunable params
        pull_tau         = getp(identity, "social_pull_tau",          0.10)
        pressure_scale   = getp(identity, "social_pressure_scale",    0.30)
        recency_decay    = getp(identity, "social_recency_decay",     50.0)  # half-life ticks
        attract_thr      = getp(identity, "social_attract_threshold",  0.15)
        repel_thr        = getp(identity, "social_repel_threshold",   -0.10)

        tick = identity.total_requests
        grid = 20  # GRID_SIZE — avoid circular import

        # -- Build identity centroid (same logic as IdentityGravityLayer)
        beliefs = identity.belief_state.beliefs
        if beliefs:
            d = len(beliefs[0].center)
            centroid = [
                sum(b.center[i] for b in beliefs) / len(beliefs)
                for i in range(d)
            ]
        else:
            centroid = [0.5] * 6

        # -- Identity mass (from previous layer or recompute)
        M_i = float(ctx.cache.extra.get("identity_mass", 1.0))
        C_ij = max(0.01, 1.0 - identity.belief_state.contradiction_score)

        # -- Compute G_social per peer
        scored: list = []
        for peer in peers[:_MAX_PEERS]:
            if peer.is_flagged:
                scored.append((peer, -0.30))   # flagged peers always repel
                continue

            # Cosine resonance
            R_ij = _cosine(centroid, peer.resonance_vec)

            # Spatial distance (normalised to [0,1])
            dx = peer.last_pos_x - habitat.pos_x
            dy = peer.last_pos_y - habitat.pos_y
            D_spatial = math.sqrt(dx * dx + dy * dy) / grid

            # Recency weight: decays if we haven't seen this peer recently
            dt = tick - peer.last_contact_tick
            recency_w = math.exp(-dt / max(1.0, recency_decay))

            G = (M_i * peer.peer_mass * max(0.0, R_ij) * C_ij * recency_w) / (D_spatial + _EPSILON)

            scored.append((peer, G))

        if not scored:
            ctx.cache.extra.update({
                "social_pull": [],
                "social_pressure": 0.0,
                "dominant_peer_id": "",
                "social_peer_count": 0,
                "aligned_peer_count": 0,
                "repelled_peer_count": 0,
            })
            return

        scored.sort(key=lambda x: x[1], reverse=True)

        # -- Social pull vector: weighted average of attracted peer resonance vecs
        dim = len(centroid)
        pull_vec  = [0.0] * dim
        pull_wsum = 0.0
        aligned   = 0
        repelled  = 0
        dominant_peer_id = ""
        dominant_G = 0.0

        for peer, G in scored:
            if G >= attract_thr:
                w = G
                rv = peer.resonance_vec
                if len(rv) == dim:
                    for i in range(dim):
                        pull_vec[i] += w * rv[i]
                    pull_wsum += w
                aligned += 1
                if abs(G) > abs(dominant_G):
                    dominant_G = G
                    dominant_peer_id = peer.peer_id
            elif G <= repel_thr:
                repelled += 1

        if pull_wsum > 0:
            pull_vec = [v / pull_wsum for v in pull_vec]

        # -- Social pressure: how strongly the outside world is calling
        # = fraction of peers that are pulling (aligned / total) * their mean G
        mean_G = sum(g for _, g in scored) / len(scored)
        social_pressure = max(0.0, min(1.0, mean_G * pressure_scale))

        # -- Nudge outer_pressure via EMA
        osc = identity.oscillation_state
        osc.outer_pressure = min(1.0,
            osc.outer_pressure * (1.0 - pull_tau) + (osc.outer_pressure + social_pressure) * pull_tau
        )

        # -- Update influence scores on peer records (EMA)
        for peer, G in scored:
            peer.influence_score = peer.influence_score * 0.85 + G * 0.15

        # -- Publish
        ctx.cache.extra["social_pull"]         = [round(v, 4) for v in pull_vec]
        ctx.cache.extra["social_pressure"]     = round(social_pressure, 4)
        ctx.cache.extra["dominant_peer_id"]    = dominant_peer_id
        ctx.cache.extra["social_peer_count"]   = len(scored)
        ctx.cache.extra["aligned_peer_count"]  = aligned
        ctx.cache.extra["repelled_peer_count"] = repelled

        logger.debug(
            "SocialFieldLayer: user=%s tick=%d peers=%d aligned=%d repelled=%d "
            "social_pressure=%.3f dominant=%s",
            identity.user_id, tick, len(scored), aligned, repelled,
            social_pressure, dominant_peer_id,
        )
