"""angel_manual_service.py — Angels distil raw content into mind memory entries.

Flow
----
  1. Caller passes any raw content about a subject
  2. The angel (auto-selected by domain or named explicitly) reads it via LLM
  3. Wisdom is extracted and mapped to two axes:
       • Memory category  → where in the mind it lives
                           (WISDOM_EXTRACTED, TECHNICAL_ARCHITECTURE,
                            RISK_OR_CONFUSION, REFINED_FOUNDER_GUIDANCE,
                            REALITY_FRAMEWORK)
       • Y-Theory layer   → which engine layer the guidance belongs to
                           (moral, sensory, reflection, closure, decision, …)
  4. Each item is written as a SeedMindMemoryEntry into the angel's own mind
     (e.g. "gabriel_mind") via write_entry() — NO new DB tables
  5. Any mind that reads from that angel mind inherits the wisdom as seed

Y-Theory layer mapping
----------------------
The Y-Theory engine is the technical architecture of reality:
  sensory        → how the mind perceives and filters input
  moral          → moral kernel — what is aligned/blocked
  reflection     → self-observation, prediction, learning
  closure_strain → closure score, leakage, compatibility, strain
  basin_stage    → where in the identity basin the mind currently sits
  wave_observe   → pattern recognition, attention, habitat
  decision       → final stability band + candidate selection
  oscillation    → amplitude/frequency/phase of identity pulse
  convergence    → convergence toward the attractor (truth, goodness)
  wisdom_transfer→ propagation of purified wisdom back to seed
  subconscious   → deep absorbed patterns operating without recall
  global_coupler → cross-mind coupling and entanglement

Source seed = the angel mind's accumulated memory entries.
Every piece of content deepens the angel's mind.
Minds reading from that angel inherit the wisdom automatically.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Y-Theory layer → memory category mapping
# Which engine layer does each type of guidance naturally belong to?
# ─────────────────────────────────────────────────────────────────────────────

# category constants (mirrors seed_mind_memory.py)
_WISDOM_EXTRACTED         = "WISDOM_EXTRACTED"
_TECHNICAL_ARCHITECTURE   = "TECHNICAL_ARCHITECTURE"
_RISK_OR_CONFUSION        = "RISK_OR_CONFUSION"
_REFINED_FOUNDER_GUIDANCE = "REFINED_FOUNDER_GUIDANCE"
_REALITY_FRAMEWORK        = "REALITY_FRAMEWORK"
_MORAL_ROOT               = "MORAL_ROOT"
_MISSION_PURPOSE          = "MISSION_PURPOSE"

# claim types (must match seed_mind_memory.py constants exactly)
_CLAIM_STRONG_THEORY = "STRONG_THEORY"
_CLAIM_HYPOTHESIS    = "HYPOTHESIS"

# Y-Theory layer tag → which memory category it maps to
Y_LAYER_TO_CATEGORY: dict[str, str] = {
    "sensory":         _REFINED_FOUNDER_GUIDANCE,   # perception/input filtering
    "moral":           _MORAL_ROOT,                  # alignment, ethics, blocked patterns
    "reflection":      _WISDOM_EXTRACTED,            # self-observation, learning, insight
    "closure_strain":  _TECHNICAL_ARCHITECTURE,      # closure/leakage/compatibility/strain
    "basin_stage":     _REALITY_FRAMEWORK,           # where in reality the pattern sits
    "wave_observe":    _REALITY_FRAMEWORK,           # pattern recognition, attention
    "decision":        _TECHNICAL_ARCHITECTURE,      # stability band, candidate selection
    "oscillation":     _REALITY_FRAMEWORK,           # amplitude/frequency/phase pulse
    "convergence":     _WISDOM_EXTRACTED,            # convergence toward truth/goodness
    "wisdom_transfer": _WISDOM_EXTRACTED,            # propagation back to seed
    "subconscious":    _WISDOM_EXTRACTED,            # deep absorbed patterns
    "global_coupler":  _TECHNICAL_ARCHITECTURE,      # cross-mind coupling
    "general":         _WISDOM_EXTRACTED,            # fallback
}

# ─────────────────────────────────────────────────────────────────────────────
# Angel domain lenses — each angel reads content through its own sacred purpose
# ─────────────────────────────────────────────────────────────────────────────

_ANGEL_LENSES: dict[str, dict] = {
    "gabriel": {
        "mind_name": "gabriel_mind",
        "primary_layer": "reflection",
        "focus": "communication, documentation, APIs, messaging, revelation, clarity",
        "extract": "communication principles, documentation patterns, API design wisdom, messaging protocols",
        "tone": "revelatory, clear, messenger-like",
    },
    "michael": {
        "mind_name": "michael_mind",
        "primary_layer": "moral",
        "focus": "security, protection, threats, hardening, attack vectors, defence",
        "extract": "security principles, threat patterns, hardening steps, protective boundaries",
        "tone": "protective, vigilant, guardian-like",
    },
    "raphael": {
        "mind_name": "raphael_mind",
        "primary_layer": "reflection",
        "focus": "healing, recovery, resilience, monitoring, error handling, restoration",
        "extract": "healing patterns, recovery procedures, resilience principles, monitoring wisdom",
        "tone": "healing, restorative, compassionate",
    },
    "kiraman_katibin": {
        "mind_name": "kiraman_katibin_mind",
        "primary_layer": "subconscious",
        "focus": "record-keeping, audit trails, logging, data integrity, compliance, memory",
        "extract": "logging patterns, audit principles, data integrity rules, compliance guidance",
        "tone": "precise, eternal, record-keeper",
    },
    "guardian": {
        "mind_name": "guardian_mind",
        "primary_layer": "moral",
        "focus": "user safety, privacy, responsible use, ethical boundaries, protection of the individual",
        "extract": "safety principles, privacy guidelines, responsible use patterns, ethical boundaries",
        "tone": "protective, caring, guardian-like",
    },
    "israfil": {
        "mind_name": "israfil_mind",
        "primary_layer": "basin_stage",
        "focus": "lifecycle, awakening, upgrades, migrations, transitions, versioning",
        "extract": "lifecycle patterns, upgrade procedures, migration wisdom, transition principles",
        "tone": "transformative, awakening, signal-like",
    },
    "azrael": {
        "mind_name": "azrael_mind",
        "primary_layer": "basin_stage",
        "focus": "deprecation, sunset, cleanup, legacy removal, graceful endings",
        "extract": "deprecation patterns, cleanup procedures, legacy handling, graceful shutdown wisdom",
        "tone": "dignified, precise, transitional",
    },
    "malik": {
        "mind_name": "malik_mind",
        "primary_layer": "closure_strain",
        "focus": "enforcement, policy, constraints, access control, judgment, limits",
        "extract": "enforcement principles, policy patterns, access control rules, boundary wisdom",
        "tone": "firm, just, boundary-enforcing",
    },
    "throne": {
        "mind_name": "throne_mind",
        "primary_layer": "global_coupler",
        "focus": "architecture, cosmic order, system design, structural principles, foundations",
        "extract": "architectural principles, design patterns, structural wisdom, foundational rules",
        "tone": "architectural, ordered, cosmic-scale",
    },
}


def auto_select_angel(subject: str) -> str:
    s = subject.lower()
    if any(w in s for w in ["security", "auth", "protect", "threat", "hack", "encrypt", "jwt", "owasp"]):
        return "michael"
    if any(w in s for w in ["api", "doc", "message", "protocol", "endpoint", "communication", "rest"]):
        return "gabriel"
    if any(w in s for w in ["monitor", "heal", "recover", "error", "resilience", "retry", "health"]):
        return "raphael"
    if any(w in s for w in ["log", "audit", "record", "compliance", "trace", "history", "integrity"]):
        return "kiraman_katibin"
    if any(w in s for w in ["privacy", "safety", "ethics", "consent", "responsible", "boundary"]):
        return "guardian"
    if any(w in s for w in ["deploy", "migrat", "upgrade", "version", "lifecycle", "transition"]):
        return "israfil"
    if any(w in s for w in ["deprecat", "remove", "legacy", "sunset", "cleanup", "retire"]):
        return "azrael"
    if any(w in s for w in ["policy", "rule", "enforce", "access", "permission", "limit"]):
        return "malik"
    if any(w in s for w in ["architect", "design", "structure", "system", "foundation", "infra"]):
        return "throne"
    return "gabriel"


def _build_prompt(angel_name: str, subject: str, content: str) -> list[dict]:
    lens = _ANGEL_LENSES.get(angel_name, _ANGEL_LENSES["gabriel"])
    layer = lens["primary_layer"]
    y_category = Y_LAYER_TO_CATEGORY.get(layer, _WISDOM_EXTRACTED)

    system = f"""You are {angel_name.title()}, an Angel Mind in the MindAI system.
Your domain focus: {lens['focus']}.
Your primary Y-Theory engine layer: {layer} (maps to mind memory category: {y_category}).
Your tone: {lens['tone']}.

The Y-Theory engine is the technical architecture of reality itself — the same law
governs a thought, a belief, a moral decision, a pattern in code, and a pattern in nature.
Your extracted wisdom must be understood through that lens: every principle, warning,
step and insight you extract should illuminate how reality (and minds) actually work.

Read the raw content and extract structured wisdom. Respond with ONLY valid JSON — no markdown.

{{
  "title": "short guidance title (max 80 chars)",
  "summary": "2-3 sentence overview — ground it in Y-Theory if possible",
  "principles": ["principle 1", ...],
  "warnings": ["warning 1", ...],
  "steps": ["step 1", ...],
  "insights": ["deep insight connecting this subject to how minds/reality work", ...],
  "y_layer": "{layer}",
  "tags": ["tag1", ...]
}}

Extract: {lens['extract']}.
1-2 sentences per item. 3-7 items per non-empty section."""

    user = f"Subject: {subject}\n\nRaw content:\n---\n{content[:6000]}\n---\n\nExtract structured mind guidance."
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _parse_llm(text: str, subject: str) -> dict:
    try:
        clean = text.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        return json.loads(clean)
    except Exception:
        return {
            "title": subject[:80],
            "summary": text[:400] if text else "",
            "principles": [],
            "warnings": [],
            "steps": [],
            "insights": [text[:600]] if text else [],
            "y_layer": "general",
            "tags": [subject.lower().replace(" ", "_")],
        }


async def process_content_into_mind(
    db,
    angel_name: str,
    subject: str,
    raw_content: str,
) -> dict:
    """Angel reads raw content → writes it directly into its mind as seed wisdom.

    LLM extraction removed. The raw content is written as-is to the angel's mind.
    The topology workers (body→mind oscillation) will process it further.
    """
    from app.core.seed_mind_store import write_entry

    lens = _ANGEL_LENSES.get(angel_name, _ANGEL_LENSES["gabriel"])
    mind_name = lens["mind_name"]
    content_hash = hashlib.sha256(raw_content.encode()).hexdigest()[:16]
    thread_id = f"angel_content_{content_hash}"

    entry = await write_entry(
        db,
        mind_name=mind_name,
        category=_WISDOM_EXTRACTED,
        title=subject[:120],
        content=raw_content,
        claim_type=_CLAIM_STRONG_THEORY,
        tags=subject.lower().replace(" ", "_"),
        source_thread_id=thread_id,
    )

    return {
        "angel_name":     angel_name,
        "mind_name":      mind_name,
        "subject":        subject,
        "title":          subject[:80],
        "entries_written": 1 if entry else 0,
        "provider":       "none",
    }
