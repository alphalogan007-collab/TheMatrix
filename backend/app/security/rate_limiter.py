"""
Rate Limiter — Per-user, per-IP, per-device rate limiting using Redis.

Applied to:
- Login endpoint (strict: 5/min)
- Advisor endpoint (moderate: 10/min)
- Screen check endpoint (moderate: 5/min)
- General API (lenient: 60/min)
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status
import redis.asyncio as aioredis


class RateLimiter:
    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def check(
        self,
        key: str,
        limit: int,
        window_seconds: int = 60,
    ) -> None:
        """
        Sliding window rate limiter.
        Raises HTTP 429 if limit is exceeded.
        """
        pipe = self._redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds)
        results = await pipe.execute()
        count = results[0]

        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please wait before retrying.",
                headers={"Retry-After": str(window_seconds)},
            )

    async def check_login(self, ip: str) -> None:
        await self.check(f"rl:login:{ip}", limit=5, window_seconds=60)

    async def check_advisor(self, user_id: str) -> None:
        await self.check(f"rl:advisor:{user_id}", limit=10, window_seconds=60)

    async def check_screen(self, user_id: str) -> None:
        await self.check(f"rl:screen:{user_id}", limit=5, window_seconds=60)

    async def check_api(self, user_id: str) -> None:
        await self.check(f"rl:api:{user_id}", limit=60, window_seconds=60)


def get_client_ip(request: Request) -> str:
    """Extract client IP, preferring X-Forwarded-For in production."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
