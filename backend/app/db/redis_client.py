"""
Redis Client — async connection pool singleton.

Provides a module-level pool so the identity store and rate limiter can share
a single connection pool without creating a new connection per request.
"""

from __future__ import annotations

import logging
from typing import Optional

import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)

_pool: Optional[aioredis.ConnectionPool] = None
_client: Optional[aioredis.Redis] = None


def _get_pool() -> aioredis.ConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = aioredis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=20,
            decode_responses=True,
        )
    return _pool


def get_redis() -> aioredis.Redis:
    """Return a shared async Redis client (uses module-level pool)."""
    global _client
    if _client is None:
        _client = aioredis.Redis(connection_pool=_get_pool())
    return _client


async def close_redis() -> None:
    """Gracefully close the Redis connection pool (call on app shutdown)."""
    global _pool, _client
    if _client is not None:
        await _client.aclose()
        _client = None
    if _pool is not None:
        await _pool.aclose()
        _pool = None
    logger.info("Redis connection pool closed.")
