"""Simple rate limiting with Redis: at most N requests per time window, per client IP.

Used on login and register, so nobody can try thousands of passwords ("brute force") or create
thousands of accounts. How it works ("fixed window"):
    key = "rl:login:<ip>:<window number>"   INCR it; the first INCR also sets it to expire with the window.
    If the count goes over the limit -> 429 Too Many Requests.
If Redis is down, requests are ALLOWED (logged): being locked out of logging in would be worse.
"""

import logging
import time
from functools import lru_cache
from typing import Protocol

from fastapi import HTTPException, Request, status
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class CounterStore(Protocol):
    def incr_with_expiry(self, key: str, seconds: int) -> int: ...


class RedisCounterStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def incr_with_expiry(self, key: str, seconds: int) -> int:
        pipe = self._redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, seconds, nx=True)  # only set the expiry on the first request of the window
        count, _ = pipe.execute()
        return int(count)


@lru_cache
def get_counter_store() -> CounterStore:
    settings = get_settings()
    return RedisCounterStore(
        Redis(host=settings.redis_host, port=settings.redis_port, socket_timeout=1, socket_connect_timeout=1)
    )


def client_ip(request: Request) -> str:
    # Behind a reverse proxy, configure it (and uvicorn --proxy-headers) so this is the real client address.
    return request.client.host if request.client else "unknown"


def rate_limit(name: str, limit: int, window_seconds: int):
    """FastAPI dependency: `Depends(rate_limit("login", 10, 60))` = at most 10 per minute per IP."""

    def check(request: Request) -> None:
        if not get_settings().rate_limit_enabled:
            return
        window = int(time.time() // window_seconds)
        key = f"rl:{name}:{client_ip(request)}:{window}"
        try:
            count = get_counter_store().incr_with_expiry(key, window_seconds)
        except RedisError:
            logger.warning("Rate limit check skipped: Redis unavailable")
            return
        if count > limit:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many attempts. Please wait a minute and try again.",
                headers={"Retry-After": str(window_seconds)},
            )

    return check
