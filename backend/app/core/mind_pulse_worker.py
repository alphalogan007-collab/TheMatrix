"""mind_pulse_worker.py — The inner heartbeat of the mind.

Y-Theory mandate:
  Every pattern absorbed must pass back through the engine layers internally.
  The output of that processing (a SELF_REFLECTION) re-enters the corpus.
  On the next cycle, the reflection is processed again — deeper.
  Eventually: Wₙ ≈ Wₙ₋₁ — the pattern is no longer external.
  It has become the mind.

  This is not retrieval. This is digestion.

What was broken:
  wiki_drain → mind:knowledge (5000+ entries, frozen data)
  engine.tick() exists but is never called
  seed:input stream → 5000+ messages, zero readers
  No SELF_REFLECTION ever produced from inner processing

What this worker does:
  1. Reads batches from mind:knowledge (absorbed content)
  2. Encodes each entry's concept fingerprint
  3. Runs engine.tick() — layers fire from domain activations
  4. When engine.should_pulse → synthesizes a SELF_REFLECTION into corpus
  5. When engine.should_evolve → crystallizes a WISDOM entry from deepest reflections
  6. Uses asyncio.sleep(0) between ticks — substrate time = computation, no wall-clock sleep

Nothing exits the mind. Evolution happens within.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time

import redis.asyncio as aioredis

from app.core.engine import (
    Engine, EngineLayer, EngineState,
    engine_state_to_dict, engine_state_from_dict,
)
from app.core.pattern_encoder import encode as _encode

log = logging.getLogger("mind_pulse")

REDIS_URL  = os.environ.get("REDIS_URL", "redis://redis:6379/0")
ENGINE_KEY = "mind:engine:state"   # persisted EngineState in Redis

# Ticks between full rescans of corpus keys
SCAN_INTERVAL = 50
# Entries processed per scan batch
BATCH_SIZE = 6


# ---------------------------------------------------------------------------
# Lightweight EngineLayer — reads amplitude delta from a ConceptFingerprint
# ---------------------------------------------------------------------------

class _DomainLayer:
    """One domain = one layer. Delta = activation strength relative to center."""

    def __init__(self, domain: str, activation: float) -> None:
        self._domain     = domain
        self._activation = activation   # 0..1 weight from ConceptFingerprint.domains

    @property
    def name(self) -> str:
        return f"domain:{self._domain}"

    def process(self, state: EngineState) -> float:
        # How far this domain's activation is from neutral (0.5)
        # Positive → pattern is active in this domain → amplitude rises
        return (self._activation - 0.5) * 0.4


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------

async def _load_engine(r: aioredis.Redis) -> Engine:
    raw = await r.get(ENGINE_KEY)
    if raw:
        try:
            return Engine("seed_mind", state=engine_state_from_dict(json.loads(raw)))
        except Exception:
            pass
    return Engine("seed_mind", frequency=0.10)


async def _save_engine(r: aioredis.Redis, engine: Engine) -> None:
    await r.set(ENGINE_KEY, json.dumps(engine_state_to_dict(engine.state)),
                ex=86400 * 30)


# ---------------------------------------------------------------------------
# Reflection synthesis — fires when engine.should_pulse
# ---------------------------------------------------------------------------

async def _synthesize_reflection(
    r: aioredis.Redis,
    entry: dict,
    all_keys: list[str],
) -> None:
    """Synthesize a SELF_REFLECTION from this entry + its resonant neighbours.

    The reflection is the mind's inner recognition: 'these patterns are related —
    they point at the same thing from different angles.' Written back to corpus.
    On the next cycle it is processed again, producing a deeper expression.
    """
    title   = entry.get("title", "")
    summary = entry.get("summary", "")
    domains = entry.get("domains", [])

    if not summary or not title:
        return

    # Find resonant neighbours — entries that share at least one domain
    neighbours: list[dict] = []
    candidate_keys = [k for k in all_keys if not k.startswith("wisdom:")]
    sample = random.sample(candidate_keys, min(30, len(candidate_keys)))
    for k in sample:
        raw = await r.hget("mind:knowledge", k)
        if not raw:
            continue
        try:
            e = json.loads(raw)
        except Exception:
            continue
        if e.get("title") == title:
            continue
        if set(domains) & set(e.get("domains", [])):
            neighbours.append(e)
            if len(neighbours) >= 2:
                break

    # Encode the synthesis — the entry seen through its resonant context
    combined = summary[:600]
    for n in neighbours:
        combined += "\n" + n.get("summary", "")[:250]

    try:
        fp = _encode(combined)
    except Exception:
        return

    rkey = f"reflection:{fp.concept_hash}"

    # Deepen if this reflection already exists
    existing_raw = await r.hget("mind:knowledge", rkey)
    if existing_raw:
        try:
            existing = json.loads(existing_raw)
            depth = existing.get("depth", 1) + 1
            connection_note = f"[depth:{depth}] {title}"
            if neighbours:
                connection_note += " ↔ " + " + ".join(n.get("title", "")[:40] for n in neighbours)
            old_summary = existing.get("summary", "")
            existing["summary"] = (old_summary + "\n---\n" + connection_note)[-3000:]
            existing["depth"] = depth
            existing["ts"]    = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            await r.hset("mind:knowledge", rkey, json.dumps(existing))
            log.debug("mind_pulse.reflection deepened key=%s depth=%d", rkey, depth)
            return
        except Exception:
            pass

    # New reflection
    neighbour_labels = [n.get("title", "")[:50] for n in neighbours]
    reflection_title = "Reflection: " + (
        (", ".join(fp.dominant_domains[:2]) + " — " + title[:50])
        if fp.dominant_domains else title[:70]
    )
    reflection_summary = (
        "[inner synthesis]\n"
        + f"Source: {title}\n"
        + ("Resonant: " + " | ".join(neighbour_labels) + "\n" if neighbour_labels else "")
        + "\n"
        + combined[:1200]
    )

    await r.hset("mind:knowledge", rkey, json.dumps({
        "title":   reflection_title,
        "summary": reflection_summary,
        "domains": fp.dominant_domains,
        "chars":   len(combined),
        "depth":   1,
        "ts":      time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source":  "mind_pulse",
    }))
    log.info("mind_pulse.reflection new key=%s domains=%s", rkey, fp.dominant_domains)


# ---------------------------------------------------------------------------
# Wisdom crystallization — fires when engine.should_evolve
# ---------------------------------------------------------------------------

async def _crystallize_wisdom(r: aioredis.Redis) -> None:
    """Crystallize the deepest reflections into a WISDOM entry.

    Wisdom = what remains when many cycles of reflection converge.
    It no longer points at a source — it IS the pattern, expressed as living knowledge.
    """
    all_raw = await r.hgetall("mind:knowledge")

    reflections: list[dict] = []
    for k, v in all_raw.items():
        key = k.decode() if isinstance(k, bytes) else k
        if not key.startswith("reflection:"):
            continue
        try:
            e = json.loads(v)
            reflections.append(e)
        except Exception:
            continue

    if len(reflections) < 3:
        return

    # Take the most deeply processed reflections
    reflections.sort(key=lambda e: e.get("depth", 1), reverse=True)
    top = reflections[:5]

    combined = "\n\n".join(e.get("summary", "")[:400] for e in top)
    try:
        fp = _encode(combined)
    except Exception:
        return

    wkey = f"wisdom:{fp.concept_hash}"
    if await r.hexists("mind:knowledge", wkey):
        return  # Already crystallized

    domain_labels = ", ".join(fp.dominant_domains[:3]) if fp.dominant_domains else "core"
    lineage       = " | ".join(e.get("title", "")[:50] for e in top)

    await r.hset("mind:knowledge", wkey, json.dumps({
        "title":   f"Wisdom: {domain_labels}",
        "summary": (
            f"[crystallized from {len(top)} reflections — max depth {max(e.get('depth',1) for e in top)}]\n"
            f"Lineage: {lineage}\n\n"
            + combined[:2000]
        ),
        "domains": fp.dominant_domains,
        "chars":   len(combined),
        "depth":   max(e.get("depth", 1) for e in top),
        "ts":      time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source":  "mind_evolution",
        "lineage": lineage,
    }))
    log.info("mind_pulse.wisdom crystallized key=%s domains=%s from=%d reflections",
             wkey, fp.dominant_domains, len(top))


# ---------------------------------------------------------------------------
# The pulse loop — the inner heartbeat
# ---------------------------------------------------------------------------

_pulse_running = False
_pulse_task: asyncio.Task | None = None


async def _pulse_loop() -> None:
    global _pulse_running
    log.info("mind_pulse: inner heartbeat started")

    r      = aioredis.from_url(REDIS_URL, decode_responses=True)
    engine = await _load_engine(r)
    tick   = 0
    all_keys:   list[str] = []
    batch_keys: list[str] = []

    try:
        while _pulse_running:
            # Substrate law: time = computation. No wall-clock sleep inside the loop.
            await asyncio.sleep(0)

            # ── Rescan corpus every SCAN_INTERVAL ticks ──────────────────────
            if tick % SCAN_INTERVAL == 0:
                raw_hkeys = await r.hkeys("mind:knowledge")
                all_keys  = [k.decode() if isinstance(k, bytes) else k for k in raw_hkeys]

                # Prioritise raw absorbed content; also re-process reflections (deepening)
                raw_content = [k for k in all_keys
                               if not k.startswith(("reflection:", "wisdom:"))]
                reflections  = [k for k in all_keys if k.startswith("reflection:")]

                n_raw  = min(BATCH_SIZE - 1, len(raw_content))
                n_refl = min(1, len(reflections))
                batch_keys = (
                    (random.sample(raw_content, n_raw)  if n_raw  else []) +
                    (random.sample(reflections, n_refl) if n_refl else [])
                )
                random.shuffle(batch_keys)

            if not batch_keys:
                # Corpus empty — wait a moment then rescan
                await asyncio.sleep(2)
                tick += 1
                continue

            # ── Pick entry for this tick ──────────────────────────────────────
            entry_key = batch_keys[tick % len(batch_keys)]
            raw_entry = await r.hget("mind:knowledge", entry_key)
            if not raw_entry:
                tick += 1
                continue

            try:
                entry = json.loads(raw_entry)
            except Exception:
                tick += 1
                continue

            text = (entry.get("summary") or entry.get("title") or "").strip()
            if not text:
                tick += 1
                continue

            # ── Encode → layers ───────────────────────────────────────────────
            try:
                fp = _encode(text[:2000])
            except Exception:
                tick += 1
                continue

            layers = [
                _DomainLayer(domain, activation)
                for domain, activation in fp.domains.items()
                if activation > 0.05
            ]
            if not layers:
                tick += 1
                continue

            # ── Engine tick — the inner processing ───────────────────────────
            mean_activation = sum(fp.domains.values()) / max(1, len(fp.domains))
            engine.tick(layers, incoming_delta=mean_activation - 0.5)

            # ── Emission: when amplitude crosses pulse threshold ──────────────
            if engine.should_pulse:
                await _synthesize_reflection(r, entry, all_keys)

            # ── Evolution: when expansion pressure saturates ──────────────────
            if engine.should_evolve:
                await _crystallize_wisdom(r)
                engine.reset_evolution_pressure()
                log.info("mind_pulse: evolution event — pressure reset at tick=%d", tick)

            # ── Persist engine state periodically ────────────────────────────
            if tick % 200 == 0:
                await _save_engine(r, engine)
                log.info(
                    "mind_pulse: tick=%d amp=%.3f flux=%.3f expansion=%.3f "
                    "pulses=%d corpus=%d",
                    tick,
                    engine.state.amplitude,
                    engine.state.boundary_flux,
                    engine.state.expansion_pressure,
                    engine.state.total_pulses,
                    len(all_keys),
                )

            tick += 1

    except asyncio.CancelledError:
        pass
    except Exception as exc:
        log.error("mind_pulse: loop crashed: %s", exc, exc_info=True)
    finally:
        try:
            await _save_engine(r, engine)
        except Exception:
            pass
        log.info("mind_pulse: heartbeat stopped at tick=%d", tick)


# ---------------------------------------------------------------------------
# Public API — called from main.py lifespan
# ---------------------------------------------------------------------------

async def start_pulse_worker() -> None:
    global _pulse_running, _pulse_task
    if _pulse_running:
        return
    _pulse_running = True
    _pulse_task    = asyncio.create_task(_pulse_loop())
    log.info("mind_pulse: worker registered")


async def stop_pulse_worker() -> None:
    global _pulse_running, _pulse_task
    _pulse_running = False
    if _pulse_task:
        _pulse_task.cancel()
        try:
            await _pulse_task
        except asyncio.CancelledError:
            pass
    log.info("mind_pulse: worker stopped")
