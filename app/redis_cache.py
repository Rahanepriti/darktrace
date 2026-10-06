import json

import redis.asyncio as redis

from app.config import settings


class HeartbeatCache:
    """Redis-backed cache for the latest crawler heartbeat."""

    def __init__(self):
        self.client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )

    @staticmethod
    def _key(worker_id: str) -> str:
        return f"darktrace:health:crawler:{worker_id}"

    async def set_heartbeat(self, heartbeat: dict) -> None:
        worker_id = heartbeat["worker_id"]

        await self.client.set(
            self._key(worker_id),
            json.dumps(heartbeat),
            ex=settings.crawler_heartbeat_ttl,
        )

    async def get_heartbeat(self, worker_id: str) -> dict | None:
        value = await self.client.get(self._key(worker_id))

        if value is None:
            return None

        return json.loads(value)

    async def get_all_heartbeats(self) -> list[dict]:
        pattern = "darktrace:health:crawler:*"

        keys = []

        async for key in self.client.scan_iter(match=pattern):
            keys.append(key)

        if not keys:
            return []

        values = await self.client.mget(keys)

        heartbeats = []

        for value in values:
            if value is not None:
                heartbeats.append(json.loads(value))

        return heartbeats

    async def delete_heartbeat(self, worker_id: str) -> None:
        await self.client.delete(self._key(worker_id))

    async def close(self) -> None:
        await self.client.aclose()
