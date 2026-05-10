"""inner_scaler.py -- Fibonacci Inner-Layer Concurrency Scaler.

Governs how many parallel consumer tasks each worker should run for its
stream. Uses Fibonacci numbers as both thresholds and target counts,
directly mirroring engine/fibonacci_scaling.py.

Architecture:
  The outer pentagon scaler (scaler.py) governs how many full CLUSTERS are
  active based on total stream lag across all domains.

  The inner layer scaler (this file) governs how many parallel CONSUMER
  TASKS run within each individual worker container based on per-layer
  stream backlog.

  Together they form a two-level Fibonacci scaling hierarchy:
    Outer:  cluster count     1 -> 2 -> 3 -> 5          (pentagon ceiling)
    Inner:  consumer count    1 -> 2 -> 3 -> 5 -> 8     (triadic ceiling = 8 = F(6))

Fibonacci law (mirroring engine/fibonacci_scaling.py):
  Thresholds are Fibonacci numbers: 5, 13, 34, 89
  Consumer counts are Fibonacci numbers: 1, 2, 3, 5, 8

  lag <  5  -> 1 consumer  (nominal, single thread)
  lag <  13 -> 2 consumers (warm up)
  lag <  34 -> 3 consumers (TRIADIC_SEED -- minimal loop)
  lag <  89 -> 5 consumers (first expansion)
  lag >= 89 -> 8 consumers (F(6) -- inner maximum, keeps loop stable)

  Scale-down hysteresis: only scale down when lag drops below 40% of tier
  threshold, preventing oscillation.

Redis keys written:
  layer:scale:{stream_key}   -> int (desired consumer count for this stream)
  layer:scale:meta           -> HASH with per-stream summary

Workers read layer:scale:{MY_STREAM} every WORKER_POLL_SEC seconds and
adjust their consumer task pool accordingly.

Env vars:
  REDIS_URL
  STREAM_PREFIXES   -- comma-separated active cluster prefixes (e.g. "ca:,cb:")
  POLL_SEC          -- how often to sample (default 15)
  MAX_CONSUMERS     -- hard ceiling per layer (default 8 = F(6))
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

POLL_SEC      = float(os.environ.get("POLL_SEC",      "15"))
MAX_CONSUMERS = int(os.environ.get("MAX_CONSUMERS",   "8"))   # F(6) -- triadic ceiling

_ALL_PREFIXES_RAW = os.environ.get("STREAM_PREFIXES", "ca:,cb:,cc:,cd:,ce:")
ALL_PREFIXES = [p.strip() for p in _ALL_PREFIXES_RAW.split(",") if p.strip()]

# Domain -> layer count (inner pentagon)
DOMAIN_LAYERS = {
    "space":   8,
    "digital": 5,
    "ether":   3,
    "aether":  2,
    "unity":   1,
}

# Fibonacci thresholds for inner scaling (lag -> consumer tier)
# Thresholds ARE Fibonacci numbers: F(5)=5, F(7)=13, F(9)=34, F(11)=89
_LAG_THRESHOLDS = [5, 13, 34, 89]   # tier 0,1,2,3,4
# Consumer counts at each tier -- Fibonacci sequence
_CONSUMER_COUNTS = [1, 2, 3, 5, 8]  # F(2),F(3),F(4),F(5),F(6)
# Scale-down hysteresis: only drop when lag < 40% of tier threshold
_HYSTERESIS = 0.40

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [INNER_SCALER] %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("inner_scaler")


# == Fibonacci tier logic ====================================================

def lag_tier(lag: int) -> int:
    """Map lag count to Fibonacci tier (0=single, 4=max=8 consumers)."""
    for i, threshold in enumerate(_LAG_THRESHOLDS):
        if lag < threshold:
            return i
    return len(_LAG_THRESHOLDS)  # tier 4 = 8 consumers


def desired_consumers(lag: int) -> int:
    """Return the target consumer count for a given stream lag."""
    t = lag_tier(lag)
    count = _CONSUMER_COUNTS[min(t, len(_CONSUMER_COUNTS) - 1)]
    return min(count, MAX_CONSUMERS)


def scale_down_lag(tier: int) -> float:
    """Hysteresis: only scale down when lag drops below this."""
    if tier == 0:
        return 0
    return _LAG_THRESHOLDS[tier - 1] * _HYSTERESIS


# == Redis measurement =======================================================

async def measure_stream_lag(redis: aioredis.Redis, stream: str) -> int:
    """Measure backlog for a single stream.

    Lag = XLEN (total messages in stream).
    Workers ACK messages after processing, so XLEN reflects unprocessed
    messages accumulating when the worker can't keep up.
    Returns 0 if stream doesn't exist.
    """
    try:
        return await redis.xlen(stream)
    except Exception:
        return 0


async def measure_all_layers(redis: aioredis.Redis, prefixes: list[str]) -> dict[str, int]:
    """Measure lag for every layer stream across all active cluster prefixes.

    Returns {stream_key: lag_count}.
    """
    lags: dict[str, int] = {}
    for prefix in prefixes:
        for domain, max_layer in DOMAIN_LAYERS.items():
            for layer in range(1, max_layer + 1):
                stream = f"{prefix}{domain}:layer{layer}"
                lags[stream] = await measure_stream_lag(redis, stream)
    return lags


# == Ring update =============================================================

async def update_layer_scales(
    redis: aioredis.Redis,
    lags: dict[str, int],
    current_scales: dict[str, int],
) -> dict[str, int]:
    """Write desired consumer counts into Redis for each stream.

    Applies hysteresis: only changes scale when clearly warranted.
    Returns updated current_scales.
    """
    meta: dict[str, str] = {}
    changed = 0

    for stream, lag in lags.items():
        new_desired = desired_consumers(lag)
        old_desired = current_scales.get(stream, 1)
        new_tier = lag_tier(lag)

        # Scale up: immediate
        if new_desired > old_desired:
            await redis.set(f"layer:scale:{stream}", new_desired)
            current_scales[stream] = new_desired
            log.info("SCALE UP   %-40s  lag=%-4d  consumers: %d -> %d  (tier %d)",
                     stream, lag, old_desired, new_desired, new_tier)
            changed += 1

        # Scale down: hysteresis
        elif new_desired < old_desired:
            down_lag = scale_down_lag(lag_tier(old_desired > 1 and
                                               _CONSUMER_COUNTS.index(old_desired) or 0))
            if lag < down_lag or lag == 0:
                await redis.set(f"layer:scale:{stream}", new_desired)
                current_scales[stream] = new_desired
                log.info("SCALE DOWN %-40s  lag=%-4d  consumers: %d -> %d",
                         stream, lag, old_desired, new_desired)
                changed += 1

        meta[stream] = json.dumps({
            "lag": lag,
            "consumers": current_scales.get(stream, old_desired),
            "tier": new_tier,
        })

    if meta:
        await redis.hset("layer:scale:meta", mapping=meta)

    if changed == 0:
        # Summarize non-trivial streams only
        hot = {s: l for s, l in lags.items() if l > 0}
        if hot:
            log.info("No changes. Hot streams: %s",
                     ", ".join(f"{s}={l}" for s, l in sorted(hot.items(), key=lambda x: -x[1])[:5]))
        else:
            log.info("All layers idle (lag=0 everywhere)")

    return current_scales


# == Main loop ===============================================================

async def run() -> None:
    log.info(
        "Inner scaler started. "
        "Thresholds: %s -> consumers: %s  (max=%d, poll=%.0fs)",
        _LAG_THRESHOLDS, _CONSUMER_COUNTS, MAX_CONSUMERS, POLL_SEC,
    )

    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    current_scales: dict[str, int] = {}

    # Read any pre-existing scale state from Redis
    try:
        existing = await redis.hgetall("layer:scale:meta")
        for stream, data_str in existing.items():
            try:
                d = json.loads(data_str)
                current_scales[stream] = d.get("consumers", 1)
            except Exception:
                pass
        if current_scales:
            log.info("Restored %d existing scale entries from Redis", len(current_scales))
    except Exception:
        pass

    while True:
        try:
            # Get currently active prefixes from cluster:active (written by outer scaler)
            active_raw = await redis.smembers("cluster:active")
            if active_raw:
                active_prefixes = [p for p in ALL_PREFIXES if p in active_raw]
            else:
                # Fall back to first prefix (ca: always active)
                active_prefixes = ALL_PREFIXES[:1]

            lags = await measure_all_layers(redis, active_prefixes)
            current_scales = await update_layer_scales(redis, lags, current_scales)

        except asyncio.CancelledError:
            break
        except Exception as exc:
            log.error("Inner scaler error: %s", exc, exc_info=True)

        await asyncio.sleep(POLL_SEC)

    await redis.aclose()
    log.info("Inner scaler stopped")


if __name__ == "__main__":
    asyncio.run(run())
