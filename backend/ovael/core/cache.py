"""Small key-value cache and fixed-window rate limiter.

Redis-backed when OVAEL_REDIS_URL is set, so every API instance shares the same scan cache and the
same rate-limit counters. Otherwise in-process, which is correct for a single instance.
"""

from __future__ import annotations

import json
import time


class Cache:
    def __init__(self, redis=None):
        self.redis = redis
        self._mem: dict[str, tuple[float, str]] = {}
        self._hits: dict[str, tuple[int, int]] = {}

    async def get_json(self, key: str):
        if self.redis is not None:
            raw = await self.redis.get(key)
        else:
            item = self._mem.get(key)
            raw = item[1] if item and item[0] > time.time() else None
        return json.loads(raw) if raw else None

    async def set_json(self, key: str, value, ttl_s: int) -> None:
        raw = json.dumps(value, default=str)
        if self.redis is not None:
            await self.redis.set(key, raw, ex=ttl_s)
        else:
            self._mem[key] = (time.time() + ttl_s, raw)

    async def delete(self, key: str) -> None:
        if self.redis is not None:
            await self.redis.delete(key)
        else:
            self._mem.pop(key, None)

    async def acquire(self, key: str, ttl_s: int) -> bool:
        """Short-lived mutex shared by every instance (SET NX EX)."""
        if self.redis is not None:
            return bool(await self.redis.set(f"lock:{key}", "1", nx=True, ex=ttl_s))
        item = self._mem.get(f"lock:{key}")
        if item and item[0] > time.time():
            return False
        self._mem[f"lock:{key}"] = (time.time() + ttl_s, "1")
        return True

    async def release(self, key: str) -> None:
        await self.delete(f"lock:{key}")

    async def hit(self, key: str, limit: int, window_s: int) -> tuple[bool, int]:
        """Count one request. Returns (allowed, seconds until the window resets)."""
        now = int(time.time())
        window = now // window_s
        reset = (window + 1) * window_s - now
        bucket = f"rl:{key}:{window}"
        if self.redis is not None:
            pipe = self.redis.pipeline()
            pipe.incr(bucket)
            pipe.expire(bucket, window_s + 1)
            count, _ = await pipe.execute()
        else:
            w, count = self._hits.get(key, (window, 0))
            count = count + 1 if w == window else 1
            self._hits[key] = (window, count)
        return count <= limit, reset
