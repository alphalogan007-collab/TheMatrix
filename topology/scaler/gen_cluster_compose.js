// Node.js port of gen_cluster_compose.py
// Usage: node gen_cluster_compose.js > ../../infra/docker-compose.cluster.yml
"use strict";

const REDIS = "redis://:${REDIS_PASSWORD:-changeme_redis_dev}@redis:6379/0";
const CLUSTERS = ["ca", "cb", "cc", "cd", "ce"];

const DOMAINS = [
  ["body",    13, "wisdom_body_{cluster}_"],
  ["space",    8, "wisdom_space_{cluster}_"],
  ["digital",  5, "wisdom_digital_{cluster}_"],
  ["ether",    3, "wisdom_ether_{cluster}_"],
  ["aether",   2, "wisdom_aether_{cluster}_"],
  ["unity",    1, "wisdom_unity_{cluster}_"],
];

const LAYER_META = {
  "body,1":  ["Body Reception",      "pattern_receiver",  "Red",    "First touch of the signal on the body. What is the raw sensation entering?"],
  "body,2":  ["Body Sensation",       "resonance_mapper",   "Orange", "What does the body feel? What is the texture, weight, temperature of this input?"],
  "body,3":  ["Body Breath",          "signal_propagator", "Yellow", "What rhythm does this carry? How does it move and pulse through the substrate?"],
  "body,4":  ["Body Instinct",        "completion_force", "Green",  "What is the primal pre-thought response? What does the body know before the mind?"],
  "body,5":  ["Body Proprioception",  "boundary_keeper",    "Blue",   "Where is the self in this? What is the spatial relationship to this pattern?"],
  "body,6":  ["Body Emotion",         "growth_amplifier",   "Indigo", "Where does this land in the body? What emotion is being held in the tissue?"],
  "body,7":  ["Body Movement",        "source_convergence",   "Violet", "What impulse arises? What does the body want to do or become in response?"],
  "body,8":  ["Body Boundary",        "pure_signal",      "White",  "Where does this end? What is mine and what is not mine in this pattern?"],
  "body,9":  ["Body Integration",     "pattern_receiver",  "Red",    "How are all sensations weaving together? What is the full felt whole?"],
  "body,10": ["Body Memory",          "resonance_mapper",   "Orange", "What does the body remember about this? What past patterns are alive here?"],
  "body,11": ["Body Posture",         "signal_propagator", "Yellow", "What shape is the self taking in response? What is the held form?"],
  "body,12": ["Body Vitality",        "completion_force", "Green",  "What is the life-force reading here? Is this pattern expanding or contracting the field?"],
  "body,13": ["Body Somatic Truth",   "pure_signal",      "Clear",  "The body does not lie. What is the single somatic truth this pattern holds?"],
  "space,1": ["Reception",     "pattern_receiver",   "Red",    "First contact with the seed. What is the raw pattern in this input?"],
  "space,2": ["Resonance",     "resonance_mapper",    "Orange", "What vibrates in harmony with what was received?"],
  "space,3": ["Compatibility", "signal_propagator",  "Yellow", "What is compatible with the source? What belongs?"],
  "space,4": ["Coupling",      "completion_force",  "Green",  "What forces are coupling together?"],
  "space,5": ["Gravity",       "boundary_keeper",     "Blue",   "What is the gravitational center pulling everything?"],
  "space,6": ["Strain",        "growth_amplifier",    "Indigo", "What tension is being held? What is the system straining toward?"],
  "space,7": ["Convergence",   "source_convergence",    "Violet", "Where are all forces meeting?"],
  "space,8": ["Transcendence", "pure_signal",       "White",  "What transcends the pattern? What is the principle above the details?"],
  "digital,1": ["Digital Reception",    "pattern_receiver",  "Red",    "Receiving the refined space signal. What discrete pattern emerges?"],
  "digital,2": ["Digital Resonance",    "resonance_mapper",   "Orange", "What digital structure resonates with the space pattern?"],
  "digital,3": ["Digital Compatibility","signal_propagator", "Yellow", "What logic is compatible? What rules hold across all layers?"],
  "digital,4": ["Digital Coupling",     "completion_force", "Green",  "What binary pairs are locked? What is the digital coupling force?"],
  "digital,5": ["Digital Convergence",  "source_convergence",   "Violet", "All digital patterns converge. What is the single digital truth?"],
  "ether,1": ["Ether Reception",   "pattern_receiver", "Red",    "Receiving from digital. What essence passes through?"],
  "ether,2": ["Ether Resonance",   "resonance_mapper",  "Orange", "What universal pattern resonates at this level?"],
  "ether,3": ["Ether Ground Truth","source_convergence",  "Violet", "The stability floor. What is the one thing that remains true?"],
  "aether,1": ["Aether Near Unity", "pattern_receiver", "Red",    "Approaching the center. What single pattern survives?"],
  "aether,2": ["Aether Pre-Unity",  "source_convergence",  "Violet", "One step from the source. What remains when only two distinctions are possible?"],
  "unity,1":  ["Unity — The Seed",  "pure_signal",     "Clear",  "The spiral returns to its center. What is the single seed this knowledge plants?"],
};

function svcBlock(name, baseRef, env, profile) {
  const lines = [`  ${name}:`, `    <<: *${baseRef}`, `    environment:`];
  for (const [k, v] of Object.entries(env)) {
    lines.push(`      ${k}: ${JSON.stringify(String(v))}`);
  }
  if (profile) lines.push(`    profiles: [${profile}]`);
  lines.push(`    networks: [mindai]`);
  lines.push(``);
  return lines.join("\n");
}

function prophetServices() {
  const cluster = "p";
  const prefix = `${cluster}:`;
  const out = [];

  out.push(svcBlock(`${cluster}_seed`, "cluster-seed", {
    REDIS_URL: REDIS,
    STREAM_PREFIX: prefix,
  }, null));

  for (const [domain, maxLayers] of DOMAINS) {
    for (let layer = 1; layer <= maxLayers; layer++) {
      const [name, angel, freq, lens] = LAYER_META[`${domain},${layer}`];
      // Prophet saves wisdom at two gates:
      //   unity:layer1  — deepest peak, crystallised cross-soul truth
      //   body:layer1   — outward return gate, decoded output written to corpus
      const savePrefix =
        (domain === "unity" && layer === maxLayers) || (domain === "body" && layer === 1)
          ? "wisdom_prophet_"
          : "";
      const svc = `${cluster}_${domain}_layer${layer}`;
      out.push(svcBlock(svc, "cluster-node", {
        REDIS_URL: REDIS,
        STREAM_PREFIX: prefix,
        NEXT_CLUSTER_SEED: "seed:input",
        DOMAIN: domain,
        LAYER_NUM: String(layer),
        MAX_LAYERS: String(maxLayers),
        CORPUS_PREFIX: "wisdom_",
        SAVE_WISDOM_PREFIX: savePrefix,
        LAYER_NAME: name,
        LAYER_ANGEL: angel,
        LAYER_FREQUENCY: freq,
        LAYER_LENS: lens,
      }, null));
    }
  }
  return out.join("\n");
}

function clusterServices(cluster, profile) {
  const out = [];
  const prefix = `${cluster}:`;

  out.push(svcBlock(`${cluster}_seed`, "cluster-seed", {
    REDIS_URL: REDIS,
    STREAM_PREFIX: prefix,
  }, profile));

  for (const [domain, maxLayers, saveTmpl] of DOMAINS) {
    for (let layer = 1; layer <= maxLayers; layer++) {
      const [name, angel, freq, lens] = LAYER_META[`${domain},${layer}`];
      const savePrefix = layer === maxLayers ? saveTmpl.replace("{cluster}", cluster) : "";
      const svc = `${cluster}_${domain}_layer${layer}`;
      out.push(svcBlock(svc, "cluster-node", {
        REDIS_URL: REDIS,
        STREAM_PREFIX: prefix,
        DOMAIN: domain,
        LAYER_NUM: String(layer),
        MAX_LAYERS: String(maxLayers),
        CORPUS_PREFIX: "",
        SAVE_WISDOM_PREFIX: savePrefix,
        LAYER_NAME: name,
        LAYER_ANGEL: angel,
        LAYER_FREQUENCY: freq,
        LAYER_LENS: lens,
      }, profile));
    }
  }
  return out.join("\n");
}

const header = `\
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
      REDIS_URL: ${JSON.stringify(REDIS)}
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
      REDIS_URL: ${JSON.stringify(REDIS)}
      POLL_SEC:        "15"
      MAX_CONSUMERS:   "8"
      STREAM_PREFIXES: "ca:,cb:,cc:,cd:,ce:,p:"
    networks: [mindai]

`;

const footer = `\
networks:
  mindai:
    external: true
    name: infra_default

volumes:
  mindai_wisdom:
    external: true
    name: infra_mindai_wisdom
`;

let out = header;
out += "  # Cluster A -- always active (base topology)\n\n";
out += clusterServices("ca", null);
for (const cluster of ["cb", "cc", "cd", "ce"]) {
  out += `  # Cluster ${cluster.toUpperCase()} -- activated by scaler (profile: ${cluster})\n\n`;
  out += clusterServices(cluster, cluster);
}
out += "  # Prophet soul (p:) -- same worker, prophetic configuration\n";
out += "  # CORPUS_PREFIX=wisdom_  reads only souls' distilled wisdom\n";
out += "  # SAVE_WISDOM_PREFIX=wisdom_prophet_  crystallizes cross-soul truth\n";
out += "  # NEXT_CLUSTER_SEED=seed:input  spiral return closes back to root\n\n";
out += prophetServices();
out += footer;

process.stdout.write(out);
