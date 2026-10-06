"""Small TTL status store. Redis is used when configured; memory mode eases local setup."""
from __future__ import annotations
import asyncio
import json
import os
import time
from typing import Any

class HealthStore:
    def __init__(self) -> None:
        self.redis_url = os.getenv("REDIS_URL", "").strip()
        self._redis = None
        self._memory: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = asyncio.Lock()
        self.ttl = int(os.getenv("HEARTBEAT_TTL_SECONDS", "60"))

    async def connect(self) -> None:
        if self.redis_url:
            try:
                from redis.asyncio import Redis
                self._redis = Redis.from_url(self.redis_url, decode_responses=True)
                await self._redis.ping()
            except Exception as exc:
                self._redis = None
                raise RuntimeError("REDIS_URL is set but Redis is not reachable.") from exc

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()

    async def put(self, worker_id: str, status: dict[str, Any]) -> None:
        payload = json.dumps(status)
        if self._redis:
            await self._redis.set(f"health:worker:{worker_id}", payload, ex=self.ttl)
            return
        async with self._lock:
            self._memory[worker_id] = (time.time() + self.ttl, status)

    async def all(self) -> list[dict[str, Any]]:
        if self._redis:
            result = []
            async for key in self._redis.scan_iter(match="health:worker:*"):
                raw = await self._redis.get(key)
                if raw:
                    result.append(json.loads(raw))
            return result
        now = time.time()
        async with self._lock:
            expired = [k for k, (deadline, _) in self._memory.items() if deadline <= now]
            for key in expired:
                del self._memory[key]
            return [item for _, item in self._memory.values()]

store = HealthStore()
