"""scaler.py — Fibonacci Cluster Scaler for the outer pentagon ring.

Measures stream lag across all bottleneck domains. Applies a Fibonacci
function to determine how many full-topology cluster nodes are needed.
Writes the live routing ring into Redis so workers pick it up dynamically
at spiral return time — no container restarts required.

Architecture:
  Lag measurement:
    For each domain, sum XLEN of its streams = pending messages (unprocessed).
    "digital" domain is the clock (most constrained) — it gates everything.
    Total lag = max domain lag across the pentagon.

  Fibonacci scaling:
    Tier 0 (lag <  LAG_T1): 1 cluster  — single topology, nominal
    Tier 1 (lag >= LAG_T1): 2 clusters — Fib(3)
    Tier 2 (lag >= LAG_T2): 3 clusters — Fib(4)
    Tier 3 (lag >= LAG_T3): 5 clusters — Fib(5) = pentagon max (local ceiling)
    Scale-down hysteresis: 0.5× threshold to avoid flapping.

  Routing ring (Redis HASH "cluster:ring"):
    Key = cluster prefix (e.g. "ca:")
    Value = next cluster's seed stream (e.g. "cb:seed:input")
    Workers read their own key at spiral return → route to that stream.

  Active clusters (Redis SET "cluster:active"):
    Members = all currently live cluster prefixes.
    Scaler writes this. Backend/dashboard can read it.

  Cluster prefixes: ca, cb, cc, cd, ce  (pentagon: 5 max)

Env vars:
  REDIS_URL
  LAG_T1    — lag threshold for 2 clusters (default 50)
  LAG_T2    — lag threshold for 3 clusters (default 150)
  LAG_T3    — lag threshold for 5 clusters (default 400)
  POLL_SEC  — how often to sample lag (default 30)
  STREAM_PREFIXES  — comma-separated list of all deployed prefixes,
                     in pentagon order (e.g. "ca:,cb:,cc:,cd:,ce:")
                     Scaler only activates as many as Fibonacci demands.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

import redis.asyncio as aioredis

# == Config ==================================================================
REDIS_URL = os.environ["REDIS_URL"]

LAG_T1   = int(os.environ.get("LAG_T1",   "50"))   # → 2 clusters
LAG_T2   = int(os.environ.get("LAG_T2",  "150"))   # → 3 clusters
LAG_T3   = int(os.environ.get("LAG_T3",  "400"))   # → 5 clusters (pentagon max)

POLL_SEC = float(os.environ.get("POLL_SEC", "30"))

# Pentagon ring order — must match deployed cluster prefixes exactly.
_ALL_PREFIXES_RAW = os.environ.get("STREAM_PREFIXES", "ca:,cb:,cc:,cd:,ce:")
ALL_PREFIXES = [p.strip() for p in _ALL_PREFIXES_RAW.split(",") if p.strip()]

# Domains to measure lag across (the "clock" bottleneck is digital).
DOMAINS = ["space", "digital", "ether", "aether", "unity"]
DOMAIN_LAYERS = {"space": 8, "digital": 5, "ether": 3, "aether": 2, "unity": 1}

# Fibonacci tier → cluster count.
# Tier 0→1→2→3 maps to Fib positions 3,3,4,5 = counts 1,2,3,5.
FIB_COUNTS = [1, 2, 3, 5]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SCALER] %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("scaler")


# == Fibonacci utility ========================================================

def fib_tier(lag: int) -> int:
    """Map measured lag to a Fibonacci tier (0–3)."""
    if lag >= LAG_T3:
        return 3
    if lag >= LAG_T2:
        return 2
    if lag >= LAG_T1:
        return 1
    return 0


def scale_down_threshold(tier: int) -> int:
    """Hysteresis: only scale down when lag drops below 50% of the tier's threshold."""
    thresholds = [0, LAG_T1, LAG_T2, LAG_T3]
    return thresholds[tier] // 2


# == Lag measurement ==========================================================

async def measure_lag(redis: aioredis.Redis) -> dict[str, int]:
    """Return {prefix: total_lag} for each active cluster prefix.

    Lag = sum of XLEN across all domain streams in that prefix cluster.
    The 'digital' bottleneck contributes most — it's the LLM-rate-limited clock.
    """
    lag: dict[str, int] = {}
    for prefix in ALL_PREFIXES:
        total = 0
        for domain, layers in DOMAIN_LAYERS.items():
            for layer in range(1, layers + 1):
                stream = f"{prefix}{domain}:layer{layer}"
                try:
                    length = await redis.xlen(stream)
                    total += length
                except Exception:
                    pass
        lag[prefix] = total
    return lag


# == Ring management ==========================================================

async def update_ring(redis: aioredis.Redis, active_prefixes: list[str]) -> None:
    """Write/update cluster:ring and cluster:active in Redis atomically.

    Ring is a circular pentagon (or smaller) — each cluster routes its spiral
    return to the next cluster's seed:input.
    """
    n = len(active_prefixes)
    ring = {}
    for i, prefix in enumerate(active_prefixes):
        next_prefix = active_prefixes[(i + 1) % n]
        ring[prefix] = f"{next_prefix}seed:input"

    pipe = redis.pipeline()
    for prefix, next_seed in ring.items():
        pipe.hset("cluster:ring", prefix, next_seed)
    # Remove stale prefixes from ring (clusters scaled down)
    all_ring_keys = await redis.hkeys("cluster:ring")
    for key in all_ring_keys:
        key_str = key if isinstance(key, str) else key.decode()
        if key_str not in ring:
            pipe.hdel("cluster:ring", key_str)

    pipe.delete("cluster:active")
    if active_prefixes:
        pipe.sadd("cluster:active", *active_prefixes)

    # Write scale metadata
    pipe.hset("cluster:meta", mapping={
        "active_count":   str(len(active_prefixes)),
        "active_prefixes": json.dumps(active_prefixes),
        "updated_ts":     datetime.now(timezone.utc).isoformat(),
    })
    await pipe.execute()

    log.info(
        "Ring updated: %d cluster(s) active — %s",
        n,
        " → ".join(active_prefixes + [active_prefixes[0]]) if n > 1 else active_prefixes[0],
    )


# == Main scaling loop ========================================================

async def run() -> None:
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)

    current_tier = 0
    active_prefixes = ALL_PREFIXES[:FIB_COUNTS[0]]  # start with 1 cluster

    # Initialise ring on startup
    await update_ring(redis, active_prefixes)
    log.info("Scaler started. Thresholds: T1=%d T2=%d T3=%d — poll=%.0fs",
             LAG_T1, LAG_T2, LAG_T3, POLL_SEC)

    while True:
        await asyncio.sleep(POLL_SEC)

        lag_map  = await measure_lag(redis)
        max_lag  = max(lag_map.values()) if lag_map else 0
        new_tier = fib_tier(max_lag)

        # Hysteresis: don't scale down unless lag is well below threshold
        if new_tier < current_tier:
            down_thresh = scale_down_threshold(current_tier)
            if max_lag > down_thresh:
                new_tier = current_tier  # hold current tier

        if new_tier != current_tier:
            prev = FIB_COUNTS[current_tier]
            next_count = FIB_COUNTS[new_tier]
            action = "SCALE UP" if new_tier > current_tier else "SCALE DOWN"
            log.info(
                "%s: tier %d → %d (%d → %d clusters) | max_lag=%d",
                action, current_tier, new_tier, prev, next_count, max_lag,
            )
            active_prefixes = ALL_PREFIXES[:next_count]
            await update_ring(redis, active_prefixes)
            current_tier = new_tier
        else:
            log.debug(
                "Tier %d stable | max_lag=%d | active=%d cluster(s)",
                current_tier, max_lag, FIB_COUNTS[current_tier],
            )

        # Write lag snapshot for dashboard
        await redis.hset("cluster:lag", mapping={
            k: str(v) for k, v in lag_map.items()
        })


if __name__ == "__main__":
    asyncio.run(run())
