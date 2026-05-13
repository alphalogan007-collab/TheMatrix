"""routes_wiki_queue.py ΓÇö Knowledge mining queue via Wikipedia + DuckDuckGo.

Workers pull topics from a Redis queue, search DuckDuckGo for context,
fetch the full Wikipedia article, and push the combined text into seed:input
for topology processing.  Designed as a bot-block-free alternative to the
YouTube drain ΓÇö works from any IP with no API key.

Redis keys:
  wiki:queue          LIST  ΓÇö pending topics (LPUSH to add, RPOP to claim)
  wiki:queue:claimed  HASH  ΓÇö topic ΓåÆ {claimed_at, worker_id}
  wiki:queue:done     LIST  ΓÇö completed {topic, chars, done_at}
  wiki:queue:dead     LIST  ΓÇö permanently failed topics
  wiki:queue:errcnt   HASH  ΓÇö topic ΓåÆ error_count

Routes:
  POST /admin/wiki/queue/enqueue        ΓÇö push one or more topics
  POST /admin/wiki/queue/enqueue-batch  ΓÇö push a preset knowledge batch
  GET  /admin/wiki/queue                ΓÇö queue stats
  DELETE /admin/wiki/queue              ΓÇö clear queue
  POST /admin/wiki/queue/drain/start    ΓÇö start background drainer
  POST /admin/wiki/queue/drain/stop     ΓÇö stop background drainer
  GET  /admin/wiki/queue/drain/status   ΓÇö drainer status + per-topic errors
  GET  /admin/wiki/queue/dead           ΓÇö list dead-lettered topics
  DELETE /admin/wiki/queue/dead         ΓÇö clear dead letters
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter
from pydantic import BaseModel

log = logging.getLogger("wiki_queue")

router = APIRouter()

REDIS_URL       = os.environ.get("REDIS_URL", "redis://redis:6379/0")
QUEUE_KEY       = "wiki:queue"
CLAIMED_KEY     = "wiki:queue:claimed"
DONE_KEY        = "wiki:queue:done"
DEAD_KEY        = "wiki:queue:dead"
ERROR_COUNT_KEY = "wiki:queue:errcnt"
MAX_RETRIES     = 3

# ΓöÇΓöÇ Default knowledge topics ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# ~300 topics covering Technology, Coding, Robotics, Automation, Machine
# Learning, Mathematics, Physics, Chemistry, Biology, Anatomy.
# At ~1 topic/second (worker + prophet combined) this gives ~5 min per cycle ΓÇö
# ~96 full passes during an 8-hour night.
DEFAULT_TOPICS: list[str] = [

    # ΓöÇΓöÇ MATHEMATICS ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    "Calculus", "Differential equations", "Partial differential equations",
    "Linear algebra", "Matrix decomposition", "Eigenvalues and eigenvectors",
    "Abstract algebra", "Group theory", "Ring theory", "Field theory",
    "Galois theory", "Number theory", "Prime numbers", "Riemann hypothesis",
    "P versus NP problem", "G├╢del's incompleteness theorems",
    "Set theory", "Topology", "Differential geometry",
    "Complex analysis", "Fourier transform", "Laplace transform",
    "Probability theory", "Bayesian statistics", "Stochastic processes",
    "Markov chains", "Monte Carlo method", "Numerical methods",
    "Convex optimization", "Graph theory", "Combinatorics",
    "Discrete mathematics", "Boolean algebra", "Category theory",
    "Measure theory", "Chaos theory", "Fractal geometry",
    "Game theory", "Information theory", "Euler's identity",
    "Fourier series", "Taylor series", "Vector calculus",

    # ΓöÇΓöÇ PHYSICS ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    "Classical mechanics", "Lagrangian mechanics", "Hamiltonian mechanics",
    "Quantum mechanics", "Quantum field theory", "Quantum electrodynamics",
    "Quantum chromodynamics", "Standard Model of particle physics",
    "General relativity", "Special relativity", "Gravitational waves",
    "Thermodynamics", "Statistical mechanics", "Entropy",
    "Electromagnetism", "Maxwell equations", "Optics", "Laser physics",
    "Fluid dynamics", "Turbulence", "Acoustics",
    "Plasma physics", "Nuclear physics", "Nuclear fusion",
    "Solid-state physics", "Semiconductor physics", "Superconductivity",
    "Condensed matter physics", "Bose-Einstein condensate", "Superfluidity",
    "Dark matter", "Dark energy", "Black holes", "Neutron stars",
    "String theory", "Quantum entanglement", "Wave-particle duality",
    "Photoelectric effect", "Uncertainty principle", "Pauli exclusion principle",
    "Higgs boson", "Particle accelerator", "Neutrino",

    # ΓöÇΓöÇ CHEMISTRY ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    "Periodic table", "Chemical bonding", "Covalent bond",
    "Acid-base chemistry", "Redox reaction", "Electrochemistry",
    "Thermochemistry", "Chemical kinetics", "Catalysis",
    "Organic chemistry", "Functional groups in organic chemistry",
    "Polymer chemistry", "Biochemistry", "Inorganic chemistry",
    "Coordination chemistry", "Nuclear chemistry",
    "Spectroscopy", "Chromatography", "Mass spectrometry",
    "Green chemistry", "Nanotechnology", "Surface chemistry",
    "Atmospheric chemistry", "Medicinal chemistry",
    "Enzyme kinetics", "Protein folding", "Lipid bilayer",
    "Oxidation states", "Gibbs free energy", "Le Chatelier's principle",

    # ΓöÇΓöÇ BIOLOGY ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    "Cell biology", "Mitosis", "Meiosis",
    "DNA replication", "RNA transcription", "Protein synthesis",
    "Gene expression", "Epigenetics", "CRISPR gene editing",
    "Genetics and heredity", "Mendelian inheritance", "Population genetics",
    "Evolution by natural selection", "Phylogenetics",
    "Cell signaling", "Apoptosis", "Stem cells",
    "Immune system", "Antibodies", "Vaccines",
    "Viruses", "Bacteria", "Archaea", "Fungi",
    "Photosynthesis", "Cellular respiration", "Mitochondria",
    "Chloroplast", "Ribosome", "Endoplasmic reticulum",
    "Plant biology", "Marine biology", "Ecology",
    "Biodiversity", "Symbiosis", "Parasitology",
    "Developmental biology", "Embryogenesis", "Regenerative medicine",
    "Microbiome", "Epigenome", "Proteomics",
    "Neuroscience", "Neural plasticity", "Memory formation",
    "Sleep physiology", "Circadian rhythm", "Consciousness",

    # ΓöÇΓöÇ ANATOMY & PHYSIOLOGY ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    "Human skeleton", "Bone structure and function",
    "Muscular system", "Skeletal muscle", "Smooth muscle", "Cardiac muscle",
    "Nervous system", "Neuron", "Synapse", "Action potential",
    "Brain anatomy", "Cerebral cortex", "Hippocampus", "Amygdala",
    "Cerebellum", "Brain stem", "Thalamus", "Hypothalamus",
    "Spinal cord", "Peripheral nervous system", "Autonomic nervous system",
    "Cardiovascular system", "Heart anatomy", "Cardiac cycle",
    "Blood vessels", "Arteries and veins", "Capillaries",
    "Blood composition", "Red blood cells", "White blood cells", "Platelets",
    "Respiratory system", "Lung anatomy", "Gas exchange",
    "Digestive system", "Stomach physiology", "Intestine", "Liver function",
    "Pancreas", "Kidney anatomy", "Nephron", "Renal filtration",
    "Endocrine system", "Hormones", "Adrenal gland", "Thyroid gland",
    "Pituitary gland", "Insulin and glucose regulation",
    "Lymphatic system", "Lymph nodes", "Spleen",
    "Integumentary system", "Skin layers", "Hair follicle",
    "Eye anatomy", "Retina and photoreceptors",
    "Ear anatomy", "Cochlea and hearing",
    "Reproductive system", "Immune cells", "Bone marrow and hematopoiesis",

    # ΓöÇΓöÇ MACHINE LEARNING & AI ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    "Artificial neural networks", "Gradient descent",
    "Backpropagation", "Convolutional neural networks",
    "Recurrent neural networks", "Long short-term memory",
    "Transformer architecture", "Attention mechanism",
    "BERT language model", "GPT language model",
    "Diffusion models", "Generative adversarial networks",
    "Variational autoencoder", "Reinforcement learning",
    "Q-learning", "Policy gradient methods",
    "Transfer learning", "Few-shot learning", "Meta-learning",
    "Federated learning", "Explainable AI",
    "Computer vision", "Image segmentation", "Object detection",
    "Natural language processing", "Word embeddings", "Tokenization",
    "Speech recognition", "Text-to-speech synthesis",
    "Recommendation systems", "Anomaly detection",
    "Time series forecasting", "Support vector machine",
    "Random forest", "Gradient boosting", "XGBoost",
    "Bayesian neural networks", "Graph neural networks",
    "Neural architecture search", "Model quantization",
    "Overfitting and regularization", "Dropout in neural networks",
    "Batch normalization", "Learning rate scheduling",
    "Embedding spaces", "Semantic search", "Vector databases",

    # ΓöÇΓöÇ PROGRAMMING & SOFTWARE ENGINEERING ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    "Python programming language", "JavaScript event loop",
    "TypeScript type system", "Rust ownership model",
    "C++ templates and metaprogramming", "Java virtual machine",
    "Functional programming", "Object-oriented programming",
    "Design patterns in software", "SOLID principles",
    "Algorithm design", "Dynamic programming",
    "Graph algorithms", "Sorting algorithms",
    "Hash table", "Binary search tree", "Heap data structure",
    "Recursion", "Concurrency and parallelism",
    "Asynchronous programming", "Coroutines",
    "Regular expressions", "Parsing and grammars",
    "Compiler design", "Interpreter design",
    "Memory management", "Garbage collection",
    "Operating system design", "Process scheduling",
    "Deadlock in operating systems", "Virtual memory",
    "Computer networking", "TCP/IP protocol",
    "HTTP protocol", "WebSocket protocol",
    "RESTful API design", "GraphQL",
    "Microservices architecture", "Event-driven architecture",
    "Database management systems", "SQL query optimization",
    "NoSQL databases", "Redis internals",
    "Git version control", "Continuous integration",
    "Test-driven development", "Clean code",
    "Containerization", "Kubernetes orchestration",
    "Linux kernel", "x86-64 architecture",

    # ΓöÇΓöÇ TECHNOLOGY & COMPUTING ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    "Quantum computing", "Quantum algorithms",
    "Cryptography", "Public-key cryptography", "Zero-knowledge proofs",
    "Blockchain technology", "Distributed ledger",
    "Internet of Things", "Edge computing", "Cloud computing",
    "5G wireless networks", "Wi-Fi technology",
    "Cybersecurity", "Intrusion detection systems",
    "GPU architecture", "CPU pipeline",
    "FPGA programming", "Embedded systems",
    "Digital signal processing", "Image compression",
    "Video encoding", "Audio codec",
    "Augmented reality", "Virtual reality",
    "Human-computer interaction", "Haptic feedback",
    "WebAssembly", "Browser rendering engine",
    "Search engine algorithms", "PageRank algorithm",
    "Distributed computing", "MapReduce",

    # ΓöÇΓöÇ ROBOTICS ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    "Robot kinematics", "Inverse kinematics",
    "Robot operating system", "Motion planning algorithms",
    "SLAM (simultaneous localization and mapping)",
    "LIDAR sensing", "Stereo vision in robotics",
    "Servo motor control", "Stepper motors",
    "PID controller", "Feedback control systems",
    "Swarm robotics", "Soft robotics",
    "Industrial robots", "Collaborative robots (cobots)",
    "Autonomous vehicles", "Drone technology",
    "Robotic surgery", "Prosthetic limbs",
    "Legged robots", "Humanoid robots",
    "Underwater robotics", "Space exploration robots",
    "Computer vision for robots", "Depth sensing",

    # ΓöÇΓöÇ AUTOMATION & CONTROL SYSTEMS ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    "Industrial automation", "Programmable logic controller",
    "SCADA systems", "Process control",
    "CNC machining", "3D printing technology",
    "Assembly line automation", "Warehouse robotics",
    "Agricultural automation", "Autonomous drones",
    "Home automation", "Smart grid technology",
    "Supply chain optimization", "Digital twin technology",
    "Predictive maintenance", "Manufacturing execution systems",
]


# ΓöÇΓöÇ helpers ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

async def _redis() -> aioredis.Redis:
    return aioredis.from_url(REDIS_URL, decode_responses=True)


def _fetch_wiki_sync(topic: str) -> tuple[str, str]:
    """Fetch Wikipedia summary + full intro section synchronously.
    Returns (title, text).  Falls back to summary if full text unavailable.
    """
    import wikipediaapi
    wiki = wikipediaapi.Wikipedia(
        language="en",
        user_agent="MindAI-KnowledgeMiner/1.0 (contact@socialfork.ca)",
    )
    page = wiki.page(topic)
    if page.exists():
        # Full article text (first 40k chars keeps it manageable)
        text = page.text[:40_000]
        return page.title, text

    # Try DuckDuckGo instant answer as fallback
    return topic, ""


def _ddg_context_sync(topic: str) -> str:
    """Get DuckDuckGo text snippets for additional context around a topic."""
    try:
        try:
            from ddgs import DDGS  # renamed from duckduckgo_search
        except ImportError:
            from duckduckgo_search import DDGS  # fallback for older installs
        with DDGS() as ddgs:
            results = list(ddgs.text(topic, max_results=5))
        snippets = []
        for r in results:
            title = r.get("title", "")
            body  = r.get("body", "")
            href  = r.get("href", "")
            if body:
                snippets.append(f"[{title}]\n{body}\nSource: {href}")
        return "\n\n".join(snippets)
    except Exception as e:
        log.debug("DDG fallback failed for %s: %s", topic, e)
        return ""


# ΓöÇΓöÇ drain state ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

_drain_task: asyncio.Task | None = None
_drain_running: bool = False
_drain_stats: dict[str, Any] = {
    "started_at":    None,
    "processed":     0,
    "errors":        0,
    "current_topic": None,
    "last_done_at":  None,
}


async def _dead_letter(r: aioredis.Redis, topic: str, reason: str, errors: int) -> None:
    dead_item = json.dumps({
        "topic":   topic,
        "errors":  errors,
        "reason":  reason[:400],
        "dead_at": datetime.now(timezone.utc).isoformat(),
    })
    await r.lpush(DEAD_KEY, dead_item)
    await r.ltrim(DEAD_KEY, 0, 4_999)
    await r.hdel(CLAIMED_KEY, topic)
    await r.hdel(ERROR_COUNT_KEY, topic)
    log.warning("wiki dead-lettered after %d errors: %s", errors, topic)


async def _drain_one(r: aioredis.Redis, topic: str) -> bool:
    """Fetch Wikipedia + DDG for one topic, push to seed:input. Returns True on success."""
    _drain_stats["current_topic"] = topic
    loop = asyncio.get_event_loop()

    try:
        wiki_title, wiki_text = await loop.run_in_executor(None, _fetch_wiki_sync, topic)
        ddg_text = await loop.run_in_executor(None, _ddg_context_sync, topic)
    except Exception as exc:
        err_msg = str(exc)
        new_count = await r.hincrby(ERROR_COUNT_KEY, topic, 1)
        log.warning("wiki drain error #%d/%d %s: %s", new_count, MAX_RETRIES, topic, err_msg[:120])
        if new_count >= MAX_RETRIES:
            await _dead_letter(r, topic, err_msg, new_count)
        else:
            backoff = 30 * (2 ** (new_count - 1))
            await asyncio.sleep(backoff)
            # re-queue at back
            await r.rpush(QUEUE_KEY, json.dumps({"topic": topic, "queued_at": datetime.now(timezone.utc).isoformat()}))
            await r.hdel(CLAIMED_KEY, topic)
        return False

    # Build combined content
    parts: list[str] = [f"Topic: {wiki_title}"]
    if wiki_text:
        parts.append(f"\n--- Wikipedia ---\n{wiki_text}")
    if ddg_text:
        parts.append(f"\n--- Web Context ---\n{ddg_text}")
    content = "\n".join(parts).strip()

    if not content or len(content) < 100:
        log.info("wiki: no content for %s, skipping", topic)
        await r.hdel(CLAIMED_KEY, topic)
        return True

    # Push to seed:input for topology
    session_id = uuid.uuid4().hex
    await r.xadd(
        "seed:input",
        {
            "input_type": "text",
            "content":    content[:50_000],
            "source":     f"wiki:{topic}",
            "session_id": session_id,
            "ts":         datetime.now(timezone.utc).isoformat(),
            "origin":     "wiki_queue_drain",
        },
        maxlen=50_000,
    )

    # Raw absorption — no imposed structure.
    # The brain absorbs text. Guidance patterns are the only categorizer.
    import hashlib as _hl
    _key = _hl.sha256(content[:500].encode()).hexdigest()[:20]
    knowledge_entry = json.dumps({
        "text":   content[:6000],
        "source": f"wiki:{wiki_title}",
        "ts":     datetime.now(timezone.utc).isoformat(),
    })
    await r.hset("mind:knowledge", _key, knowledge_entry)

    # Done record
    done_item = json.dumps({
        "topic":      wiki_title,
        "chars":      len(content),
        "done_at":    datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
    })
    await r.lpush(DONE_KEY, done_item)
    await r.ltrim(DONE_KEY, 0, 9_999)
    await r.hdel(CLAIMED_KEY, topic)

    # Emit spirit:events pulse so cloud world viewer reacts
    ts_now    = datetime.now(timezone.utc).isoformat()
    layer_num = min(8, max(1, (len(content) // 5_000) + 1))
    await r.xadd(
        "spirit:events",
        {
            "type":       "layer_done",
            "mind_name":  f"space_layer{layer_num}",
            "layer_num":  str(layer_num),
            "layer":      f"space:layer{layer_num}",
            "ts":         ts_now,
            "session_id": session_id,
            "topic":      f"wiki:{wiki_title[:120]}",
            "direction":  "descending",
            "output":     (
                f"[Knowledge Absorbed]\nTopic: {wiki_title}\n"
                f"Chars: {len(content)}\nSource: Wikipedia + DuckDuckGo\n"
                f"[affinity={min(99.0, len(content) / 500):.4f}]"
            ),
        },
        maxlen=50_000,
    )

    _drain_stats["processed"]    += 1
    _drain_stats["last_done_at"]  = ts_now
    log.info("wiki Γ£ô %s (%d chars)", wiki_title[:60], len(content))
    return True


async def _drain_loop() -> None:
    """Background loop: drain wiki:queue one topic at a time."""
    global _drain_running
    log.info("Wiki drainer started (MAX_RETRIES=%d)", MAX_RETRIES)
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        while _drain_running:
            raw = await r.rpop(QUEUE_KEY)
            if not raw:
                # Queue empty ΓÇö re-seed default topics so world never goes dark
                log.info("Wiki queue empty, re-seeding %d default topics", len(DEFAULT_TOPICS))
                for topic in DEFAULT_TOPICS:
                    await r.lpush(QUEUE_KEY, json.dumps({
                        "topic":     topic,
                        "queued_at": datetime.now(timezone.utc).isoformat(),
                    }))
                await asyncio.sleep(15)  # brief pause before resuming
                continue

            try:
                entry = json.loads(raw)
            except Exception:
                continue

            topic = entry.get("topic", "")
            if not topic:
                continue

            # Skip already-dead topics
            existing_errors = int(await r.hget(ERROR_COUNT_KEY, topic) or 0)
            if existing_errors >= MAX_RETRIES:
                await _dead_letter(r, topic, "skipped: already exceeded max retries", existing_errors)
                continue

            # Mark claimed
            await r.hset(CLAIMED_KEY, topic, json.dumps({
                "claimed_at": datetime.now(timezone.utc).isoformat(),
                "attempt":    existing_errors + 1,
            }))

            try:
                ok = await _drain_one(r, topic)
                if ok:
                    await r.hdel(ERROR_COUNT_KEY, topic)
                else:
                    _drain_stats["errors"] += 1
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("wiki drain loop unhandled: %s", exc)
                _drain_stats["errors"] += 1

            if _drain_running:
                await asyncio.sleep(3)  # courtesy pause between topics
    finally:
        _drain_stats["current_topic"] = None
        await r.aclose()
        log.info("Wiki drainer stopped (processed=%d errors=%d)",
                 _drain_stats["processed"], _drain_stats["errors"])


async def _ensure_wiki_drain_running() -> None:
    """Start the wiki drainer if not already running. Safe to call from lifespan."""
    global _drain_task, _drain_running
    if _drain_task and not _drain_task.done():
        return
    _drain_running = True
    _drain_stats["started_at"] = datetime.now(timezone.utc).isoformat()
    _drain_stats["processed"]  = 0
    _drain_stats["errors"]     = 0
    _drain_task = asyncio.create_task(_drain_loop())


async def _seed_default_topics() -> int:
    """Push DEFAULT_TOPICS into wiki:queue if queue is empty. Returns topics pushed."""
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        existing = await r.llen(QUEUE_KEY)
        if existing > 0:
            return 0
        pushed = 0
        for topic in DEFAULT_TOPICS:
            await r.lpush(QUEUE_KEY, json.dumps({
                "topic":     topic,
                "queued_at": datetime.now(timezone.utc).isoformat(),
            }))
            pushed += 1
        log.info("Wiki queue seeded with %d default topics", pushed)
        return pushed
    finally:
        await r.aclose()


# ΓöÇΓöÇ routes ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

class EnqueueBody(BaseModel):
    topics: list[str]


@router.post("/admin/wiki/queue/enqueue")
async def wiki_enqueue(body: EnqueueBody):
    """Push one or more knowledge topics into the wiki queue."""
    if not body.topics:
        return {"queued": 0}
    r = await _redis()
    try:
        pushed = 0
        for t in body.topics:
            t = t.strip()
            if not t:
                continue
            await r.lpush(QUEUE_KEY, json.dumps({
                "topic":     t,
                "queued_at": datetime.now(timezone.utc).isoformat(),
            }))
            pushed += 1
        return {"queued": pushed, "total_pending": await r.llen(QUEUE_KEY)}
    finally:
        await r.aclose()


@router.post("/admin/wiki/queue/enqueue-batch")
async def wiki_enqueue_batch():
    """Push the full default knowledge batch (physics/math/bio/CS) into the queue."""
    r = await _redis()
    try:
        pushed = 0
        for t in DEFAULT_TOPICS:
            await r.lpush(QUEUE_KEY, json.dumps({
                "topic":     t,
                "queued_at": datetime.now(timezone.utc).isoformat(),
            }))
            pushed += 1
        return {"queued": pushed, "total_pending": await r.llen(QUEUE_KEY)}
    finally:
        await r.aclose()


@router.get("/admin/wiki/queue")
async def wiki_queue_status():
    """Queue depth, claimed, done, dead counts."""
    r = await _redis()
    try:
        pending = await r.llen(QUEUE_KEY)
        claimed = await r.hlen(CLAIMED_KEY)
        done    = await r.llen(DONE_KEY)
        dead    = await r.llen(DEAD_KEY)
        raw_top = await r.lrange(QUEUE_KEY, -10, -1)
        top = [json.loads(x).get("topic", "?") for x in reversed(raw_top)]
        return {
            "pending": pending, "claimed": claimed,
            "done": done, "dead": dead, "next_10": top,
        }
    finally:
        await r.aclose()


@router.delete("/admin/wiki/queue")
async def wiki_queue_clear():
    r = await _redis()
    try:
        count = await r.llen(QUEUE_KEY)
        await r.delete(QUEUE_KEY)
        return {"cleared": count}
    finally:
        await r.aclose()


@router.post("/admin/wiki/queue/drain/start")
async def wiki_drain_start():
    await _ensure_wiki_drain_running()
    return {"started": True, "stats": _drain_stats}


@router.post("/admin/wiki/queue/drain/stop")
async def wiki_drain_stop():
    global _drain_running, _drain_task
    _drain_running = False
    if _drain_task:
        _drain_task.cancel()
    return {"stopped": True, "stats": _drain_stats}


@router.get("/admin/wiki/queue/drain/status")
async def wiki_drain_status():
    r = await _redis()
    try:
        pending    = await r.llen(QUEUE_KEY)
        done       = await r.llen(DONE_KEY)
        dead       = await r.llen(DEAD_KEY)
        err_counts = await r.hgetall(ERROR_COUNT_KEY)
    finally:
        await r.aclose()
    return {
        "running":          _drain_running and bool(_drain_task and not _drain_task.done()),
        "stats":            _drain_stats,
        "pending":          pending,
        "done":             done,
        "dead_letters":     dead,
        "max_retries":      MAX_RETRIES,
        "per_topic_errors": {t: int(c) for t, c in err_counts.items()},
    }


@router.get("/admin/wiki/queue/dead")
async def wiki_queue_dead(count: int = 50):
    r = await _redis()
    try:
        raw_items = await r.lrange(DEAD_KEY, 0, count - 1)
    finally:
        await r.aclose()
    items = []
    for raw in raw_items:
        try:
            items.append(json.loads(raw))
        except Exception:
            pass
    return {"dead_letters": items, "total": len(items)}


@router.delete("/admin/wiki/queue/dead")
async def wiki_queue_clear_dead():
    r = await _redis()
    try:
        dead_count = await r.llen(DEAD_KEY)
        await r.delete(DEAD_KEY)
        await r.delete(ERROR_COUNT_KEY)
    finally:
        await r.aclose()
    return {"cleared_dead_letters": dead_count}
