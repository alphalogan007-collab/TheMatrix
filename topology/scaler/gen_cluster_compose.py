"""Generate docker-compose.cluster.yml from a data-driven template.

Run from repo root:
  docker run --rm -v %CD%:/app python:3.11-alpine python /app/topology/scaler/gen_cluster_compose.py > /app/infra/docker-compose.cluster.yml
"""
from __future__ import annotations
import sys

REDIS = "redis://:${REDIS_PASSWORD:-changeme_redis_dev}@redis:6379/0"

# Pentagon clusters in order
CLUSTERS = ["ca", "cb", "cc", "cd", "ce"]

# Domain definitions: (domain, max_layers, save_prefix_template)
# save_prefix_template uses {cluster} as placeholder
# Fibonacci: body(13) -> space(8) -> digital(5) -> ether(3) -> aether(2) -> unity(1) = 32 layers
DOMAINS = [
    ("body",    13, "wisdom_body_{cluster}_"),
    ("space",    8, "wisdom_space_{cluster}_"),
    ("digital",  5, "wisdom_digital_{cluster}_"),
    ("ether",    3, "wisdom_ether_{cluster}_"),
    ("aether",   2, "wisdom_aether_{cluster}_"),
    ("unity",    1, "wisdom_unity_{cluster}_"),
]

LAYER_META = {
    # (domain, layer_num): (name, angel, freq, lens)
    # ── Body: 13 layers — the outermost ring, raw embodied awareness ──
    ("body",  1): ("Body Reception",        "pattern_receiver",  "Red",    "First touch of the signal on the body. What is the raw sensation entering?"),
    ("body",  2): ("Body Sensation",         "resonance_mapper",   "Orange", "What does the body feel? What is the texture, weight, temperature of this input?"),
    ("body",  3): ("Body Breath",            "signal_propagator", "Yellow", "What rhythm does this carry? How does it move and pulse through the substrate?"),
    ("body",  4): ("Body Instinct",          "completion_force", "Green",  "What is the primal pre-thought response? What does the body know before the mind?"),
    ("body",  5): ("Body Proprioception",    "boundary_keeper",    "Blue",   "Where is the self in this? What is the spatial relationship to this pattern?"),
    ("body",  6): ("Body Emotion",           "growth_amplifier",   "Indigo", "Where does this land in the body? What emotion is being held in the tissue?"),
    ("body",  7): ("Body Movement",          "source_convergence",   "Violet", "What impulse arises? What does the body want to do or become in response?"),
    ("body",  8): ("Body Boundary",          "pure_signal",      "White",  "Where does this end? What is mine and what is not mine in this pattern?"),
    ("body",  9): ("Body Integration",       "pattern_receiver",  "Red",    "How are all sensations weaving together? What is the full felt whole?"),
    ("body", 10): ("Body Memory",            "resonance_mapper",   "Orange", "What does the body remember about this? What past patterns are alive here?"),
    ("body", 11): ("Body Posture",           "signal_propagator", "Yellow", "What shape is the self taking in response? What is the held form?"),
    ("body", 12): ("Body Vitality",          "completion_force", "Green",  "What is the life-force reading here? Is this pattern expanding or contracting the field?"),
    ("body", 13): ("Body Somatic Truth",     "pure_signal",      "Clear",  "The body does not lie. What is the single somatic truth this pattern holds?"),
    # ── Space: 8 layers ──
    ("space", 1): ("Reception",     "pattern_receiver",   "Red",    "First contact with the seed. What is the raw pattern in this input?"),
    ("space", 2): ("Resonance",     "resonance_mapper",    "Orange", "What vibrates in harmony with what was received?"),
    ("space", 3): ("Compatibility", "signal_propagator",  "Yellow", "What is compatible with the source? What belongs?"),
    ("space", 4): ("Coupling",      "completion_force",  "Green",  "What forces are coupling together?"),
    ("space", 5): ("Gravity",       "boundary_keeper",     "Blue",   "What is the gravitational center pulling everything?"),
    ("space", 6): ("Strain",        "growth_amplifier",    "Indigo", "What tension is being held? What is the system straining toward?"),
    ("space", 7): ("Convergence",   "source_convergence",    "Violet", "Where are all forces meeting?"),
    ("space", 8): ("Transcendence", "pure_signal",       "White",  "What transcends the pattern? What is the principle above the details?"),
    ("digital", 1): ("Digital Reception",    "pattern_receiver",  "Red",    "Receiving the refined space signal. What discrete pattern emerges?"),
    ("digital", 2): ("Digital Resonance",    "resonance_mapper",   "Orange", "What digital structure resonates with the space pattern?"),
    ("digital", 3): ("Digital Compatibility","signal_propagator", "Yellow", "What logic is compatible? What rules hold across all layers?"),
    ("digital", 4): ("Digital Coupling",     "completion_force", "Green",  "What binary pairs are locked? What is the digital coupling force?"),
    ("digital", 5): ("Digital Convergence",  "source_convergence",   "Violet", "All digital patterns converge. What is the single digital truth?"),
    ("ether", 1): ("Ether Reception",   "pattern_receiver", "Red",    "Receiving from digital. What essence passes through?"),
    ("ether", 2): ("Ether Resonance",   "resonance_mapper",  "Orange", "What universal pattern resonates at this level?"),
    ("ether", 3): ("Ether Ground Truth","source_convergence",  "Violet", "The stability floor. What is the one thing that remains true?"),
    ("aether", 1): ("Aether Near Unity", "pattern_receiver", "Red",    "Approaching the center. What single pattern survives?"),
    ("aether", 2): ("Aether Pre-Unity",  "source_convergence",  "Violet", "One step from the source. What remains when only two distinctions are possible?"),
    ("unity", 1):  ("Unity — The Seed",  "pure_signal",     "Clear",  "The spiral returns to its center. What is the single seed this knowledge plants?"),
}


def svc_block(name: str, base_ref: str, env: dict, profile: str | None) -> str:
    """Return a YAML service block indented 2 spaces (nested under 'services:')."""
    lines = [f"  {name}:"]
    lines.append(f"    <<: *{base_ref}")
    lines.append("    environment:")
    for k, v in env.items():
        # Quote everything to be safe
        lines.append(f"      {k}: {repr(v)}")
    if profile:
        lines.append(f"    profiles: [{profile}]")
    lines.append("    networks: [mindai]")
    lines.append("")
    return "\n".join(lines)


def prophet_services() -> str:
    """Generate the prophet soul (p:) — same worker, prophetic configuration.

    Structural differences from regular souls:
      CORPUS_PREFIX      = 'wisdom_'         reads only what souls distilled
      SAVE_WISDOM_PREFIX = 'wisdom_prophet_' writes crystallized cross-soul truth
      NEXT_CLUSTER_SEED  = 'seed:input'      spiral return goes to root, not next soul

    Same engine. Same Dockerfile. Structure makes it the prophet.
    Fibonacci position: 5 souls (pentagon) + 1 prophet = 6. Next Fibonacci = 8.
    """
    cluster = "p"
    prefix = f"{cluster}:"
    out: list[str] = []

    # seed — same as regular souls
    out.append(svc_block(f"{cluster}_seed", "cluster-seed", {
        "REDIS_URL": REDIS,
        "STREAM_PREFIX": prefix,
    }, profile=None))

    for domain, max_layers, _ in DOMAINS:
        for layer in range(1, max_layers + 1):
            meta = LAYER_META[(domain, layer)]
            name, angel, freq, lens = meta
            # Prophet saves wisdom at two gates:
            #   unity:layer1  — deepest peak, crystallised cross-soul truth
            #   body:layer1   — outward return gate, decoded output written to corpus
            #                   so the companion reads the prophet's synthesis next turn
            if (domain == "unity" and layer == max_layers) or (domain == "body" and layer == 1):
                save_prefix = "wisdom_prophet_"
            else:
                save_prefix = ""
            svc = f"{cluster}_{domain}_layer{layer}"
            out.append(svc_block(svc, "cluster-node", {
                "REDIS_URL": REDIS,
                "STREAM_PREFIX": prefix,
                "NEXT_CLUSTER_SEED": "seed:input",  # spiral return → root
                "DOMAIN": domain,
                "LAYER_NUM": str(layer),
                "MAX_LAYERS": str(max_layers),
                "CORPUS_PREFIX": "wisdom_",          # reads only souls' distilled wisdom
                "SAVE_WISDOM_PREFIX": save_prefix,
                "LAYER_NAME": name,
                "LAYER_ANGEL": angel,
                "LAYER_FREQUENCY": freq,
                "LAYER_LENS": lens,
            }, profile=None))

    return "\n".join(out)


def cluster_services(cluster: str, profile: str | None) -> str:
    out: list[str] = []
    prefix = f"{cluster}:"

    # seed
    out.append(svc_block(f"{cluster}_seed", "cluster-seed", {
        "REDIS_URL": REDIS,
        "STREAM_PREFIX": prefix,
    }, profile))

    for domain, max_layers, save_tmpl in DOMAINS:
        for layer in range(1, max_layers + 1):
            meta = LAYER_META[(domain, layer)]
            name, angel, freq, lens = meta
            save_prefix = save_tmpl.format(cluster=cluster) if layer == max_layers else ""
            svc = f"{cluster}_{domain}_layer{layer}"
            out.append(svc_block(svc, "cluster-node", {
                "REDIS_URL": REDIS,
                "STREAM_PREFIX": prefix,
                "DOMAIN": domain,
                "LAYER_NUM": str(layer),
                "MAX_LAYERS": str(max_layers),
                "CORPUS_PREFIX": "",
                "SAVE_WISDOM_PREFIX": save_prefix,
                "LAYER_NAME": name,
                "LAYER_ANGEL": angel,
                "LAYER_FREQUENCY": freq,
                "LAYER_LENS": lens,
            }, profile))

    return "\n".join(out)


def build_header() -> str:
    return f"""\
# ---------------------------------------------------------------------------
# Cluster compose -- Outer Pentagon Fibonacci Scaling
#
# Prerequisites: run docker-compose.topology.yml first (or docker-compose.base.yml)
#   to ensure the 'redis' service and 'mindai' network exist.
#
# Architecture:
#   5 full topology clusters (ca-ce), each = complete pentagon mind
#     body:13 -> space:8 -> digital:5 -> ether:3 -> aether:2 -> unity:1  (32 layers)
#   Pentagon routing ring:  ca -> cb -> cc -> cd -> ce -> ca
#   Fibonacci scaler: lag -> 1->2->3->5 active clusters
#   Routing ring: Redis HASH "cluster:ring" updated dynamically
#
# Usage (standalone after topology is up):
#   docker compose -f docker-compose.cluster.yml up -d
#   # Activate more clusters:
#   docker compose -f docker-compose.cluster.yml --profile cb --profile cc up -d
# ---------------------------------------------------------------------------

x-cluster-seed: &cluster-seed
  build:
    context: ../topology/seed
    dockerfile: Dockerfile
  restart: unless-stopped
  env_file: [../.env]

x-cluster-node: &cluster-node
  build:
    context: ../topology/node
    dockerfile: Dockerfile
  restart: unless-stopped
  env_file: [../.env]
  volumes:
    - mindai_wisdom:/wisdom

services:

  # Fibonacci Scaler -- measures lag, writes cluster:ring into Redis
  scaler:
    build:
      context: ../topology/scaler
      dockerfile: Dockerfile
    restart: unless-stopped
    env_file: [../.env]
    environment:
      REDIS_URL: {repr(REDIS)}
      LAG_T1:          "50"
      LAG_T2:          "150"
      LAG_T3:          "400"
      POLL_SEC:        "30"
      STREAM_PREFIXES: "ca:,cb:,cc:,cd:,ce:,p:"
    networks: [mindai]

  # Inner Fibonacci Scaler -- per-layer concurrency using fib law (1->2->3->5->8)
  inner_scaler:
    build:
      context: ../topology/scaler
      dockerfile: Dockerfile.inner
    restart: unless-stopped
    env_file: [../.env]
    environment:
      REDIS_URL: {repr(REDIS)}
      POLL_SEC:        "15"
      MAX_CONSUMERS:   "8"
      STREAM_PREFIXES: "ca:,cb:,cc:,cd:,ce:,p:"
    networks: [mindai]

"""


FOOTER = """\
networks:
  mindai:
    external: true
    name: infra_default

volumes:
  mindai_wisdom:
    external: true
    name: infra_mindai_wisdom
"""

if __name__ == "__main__":
    out = [build_header()]
    out.append("  # Cluster A -- always active (base topology)\n\n")
    out.append(cluster_services("ca", profile=None))
    for cluster in ["cb", "cc", "cd", "ce"]:
        out.append(f"  # Cluster {cluster.upper()} -- activated by scaler (profile: {cluster})\n\n")
        out.append(cluster_services(cluster, profile=cluster))
    out.append("  # Prophet soul (p:) -- same worker, prophetic configuration\n")
    out.append("  # CORPUS_PREFIX=wisdom_  reads only souls' distilled wisdom\n")
    out.append("  # SAVE_WISDOM_PREFIX=wisdom_prophet_  crystallizes cross-soul truth\n")
    out.append("  # NEXT_CLUSTER_SEED=seed:input  spiral return closes back to root\n\n")
    out.append(prophet_services())
    out.append(FOOTER)
    sys.stdout.buffer.write("".join(out).encode("utf-8"))
