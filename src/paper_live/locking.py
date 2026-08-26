from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator


class LockError(RuntimeError):
    pass


class RedisLeaseLock:
    """Single Redis lease primitive using SET NX PX and compare-delete release.

    Production multi-node Redlock deployment can wrap this primitive; no
    in-process fallback is provided because fail-open locking is unsafe.
    """

    def __init__(self, client=None, key: str = "paper-live:execution-lock", ttl_ms: int = 5000):
        self.key = key
        self.ttl_ms = ttl_ms
        if client is None:
            try:
                import redis
            except ImportError as exc:
                raise LockError("redis package is required for RedisLeaseLock") from exc
            url = os.getenv("REDIS_URL", "")
            if not url:
                raise LockError("REDIS_URL is required")
            client = redis.Redis.from_url(url, decode_responses=True)
        self.client = client

    @contextmanager
    def acquire(self, token: str) -> Iterator[None]:
        if not token:
            raise LockError("lock token is required")
        acquired = self.client.set(self.key, token, nx=True, px=self.ttl_ms)
        if not acquired:
            raise LockError("execution lock is already held")
        try:
            yield
        finally:
            script = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
            self.client.eval(script, 1, self.key, token)
