from __future__ import annotations

from typing import List, Protocol

from .schemas import HeartbeatPayload


class HeartbeatCache(Protocol):
    async def record_heartbeat(self, payload: HeartbeatPayload) -> None: ...

    async def get_all_heartbeats(self) -> List[HeartbeatPayload]: ...


class RedisHeartbeatCache:
    def __init__(self, redis_client, key_prefix: str, ttl_seconds: int) -> None:
        self._redis = redis_client
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds

    def _key_for(self, worker_id: str) -> str:
        return f"{self._key_prefix}{worker_id}"

    async def record_heartbeat(self, payload: HeartbeatPayload) -> None:
        await self._redis.set(
            self._key_for(payload.worker_id),
            payload.model_dump_json(),
            ex=self._ttl_seconds,
        )

    async def get_all_heartbeats(self) -> List[HeartbeatPayload]:
        pattern = f"{self._key_prefix}*"
        keys: List[str] = []
        async for key in self._redis.scan_iter(match=pattern):
            keys.append(key)
        if not keys:
            return []
        raw_values = await self._redis.mget(keys)
        heartbeats: List[HeartbeatPayload] = []
        for raw in raw_values:
            if raw is None:
                continue
            try:
                heartbeats.append(HeartbeatPayload.model_validate_json(raw))
            except (ValueError, TypeError):
                continue
        return heartbeats


class InMemoryHeartbeatCache:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def record_heartbeat(self, payload: HeartbeatPayload) -> None:
        self._store[payload.worker_id] = payload.model_dump_json()

    async def get_all_heartbeats(self) -> List[HeartbeatPayload]:
        heartbeats: List[HeartbeatPayload] = []
        for raw in self._store.values():
            try:
                heartbeats.append(HeartbeatPayload.model_validate_json(raw))
            except (ValueError, TypeError):
                continue
        return heartbeats

    def expire(self, worker_id: str) -> None:
        self._store.pop(worker_id, None)
