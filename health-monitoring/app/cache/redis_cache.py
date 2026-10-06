"""Redis heartbeat cache. Every Redis call is bounded by a timeout."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable

from pydantic import ValidationError
from redis.exceptions import RedisError

from app.core.logging import get_logger, log_event
from app.schemas.health import Heartbeat

log = get_logger("cache")

HEARTBEAT_PREFIX = "crawler:heartbeat:"   # + worker_id, JSON, EX = TTL
LAST_SEEN_KEY = "crawler:last_seen"        # hash worker_id -> server receive time (outlives the TTL)
NONCE_PREFIX = "crawler:nonce:"            # replay protection


class CacheUnavailable(Exception):
    pass


@dataclass
class CacheSnapshot:
    fresh: list[Heartbeat] = field(default_factory=list)  # heartbeat key still alive (within TTL)
    last_seen: dict[str, datetime] = field(default_factory=dict)  # every known worker


class HeartbeatCache:
    def __init__(self, redis: Any, ttl_seconds: int, timeout_seconds: float, forget_after_seconds: int = 3600):
        self._redis = redis
        self._ttl = ttl_seconds
        self._timeout = timeout_seconds
        self._forget = forget_after_seconds

    async def _guard(self, coro: Awaitable[Any]) -> Any:
        try:
            return await asyncio.wait_for(coro, self._timeout)
        except (asyncio.TimeoutError, RedisError, OSError) as exc:
            raise CacheUnavailable(type(exc).__name__) from None

    async def ping(self) -> None:
        await self._guard(self._redis.ping())

    async def store(self, hb: Heartbeat, received_at: datetime | None = None) -> None:
        received = (received_at or datetime.now(timezone.utc)).isoformat()

        async def _do() -> None:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.set(HEARTBEAT_PREFIX + hb.worker_id, hb.model_dump_json(), ex=self._ttl)
                pipe.hset(LAST_SEEN_KEY, hb.worker_id, received)
                pipe.expire(LAST_SEEN_KEY, self._forget)
                await pipe.execute()

        await self._guard(_do())

    async def claim_nonce(self, nonce_hex: str, ttl_seconds: int) -> bool:
        """True if the nonce was unseen (and is now recorded); False means replay."""
        res = await self._guard(self._redis.set(NONCE_PREFIX + nonce_hex, "1", nx=True, ex=ttl_seconds))
        return bool(res)

    async def snapshot(self, now: datetime | None = None) -> CacheSnapshot:
        now = now or datetime.now(timezone.utc)

        async def _do() -> tuple[dict, list]:
            seen = await self._redis.hgetall(LAST_SEEN_KEY)
            ids = list(seen)
            vals = await self._redis.mget([HEARTBEAT_PREFIX + i for i in ids]) if ids else []
            return seen, vals

        seen_raw, vals = await self._guard(_do())
        snap = CacheSnapshot()
        expired: list[str] = []
        for wid, raw in seen_raw.items():
            try:
                seen_at = datetime.fromisoformat(raw)
            except ValueError:
                expired.append(wid)
                continue
            if (now - seen_at).total_seconds() > self._forget:
                expired.append(wid)
                continue
            snap.last_seen[wid] = seen_at
        for wid, val in zip(list(seen_raw), vals):
            if val is None or wid not in snap.last_seen:
                continue
            try:
                snap.fresh.append(Heartbeat.model_validate_json(val))
            except ValidationError:
                log_event(log, logging.WARNING, "corrupt heartbeat cache entry", worker_id=wid)
        if expired:  # best-effort pruning of decommissioned workers
            try:
                await self._guard(self._redis.hdel(LAST_SEEN_KEY, *expired))
            except CacheUnavailable:
                pass
        return snap
