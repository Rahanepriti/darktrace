"""Consolidated health: runs component checks concurrently within a strict time budget."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Awaitable, Callable

from app.cache.redis_cache import HeartbeatCache
from app.core.config import Settings
from app.core.logging import get_logger, log_event
from app.schemas.health import (
    Components,
    CrawlerComponent,
    DatabaseComponent,
    DetailedHealthResponse,
    HealthStatus,
)
from app.services.crawler_health import check_crawler

log = get_logger("health_service")

DbCheck = Callable[[], Awaitable[DatabaseComponent]]


def aggregate(*statuses: HealthStatus) -> HealthStatus:
    if HealthStatus.unhealthy in statuses:
        return HealthStatus.unhealthy
    if HealthStatus.degraded in statuses:
        return HealthStatus.degraded
    return HealthStatus.healthy


class HealthService:
    def __init__(self, settings: Settings, cache: HeartbeatCache, db_check: DbCheck):
        self._s = settings
        self._cache = cache
        self._db_check = db_check
        self._lock = asyncio.Lock()
        self._last: tuple[float, DetailedHealthResponse] | None = None

    async def check(self) -> DetailedHealthResponse:
        db_task = asyncio.ensure_future(self._db_check())
        crawler_task = asyncio.ensure_future(check_crawler(self._cache, self._s.crawler_unhealthy_after_seconds))
        _, pending = await asyncio.wait({db_task, crawler_task}, timeout=self._s.health_budget_seconds)
        for t in pending:
            t.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        db = self._result(db_task, DatabaseComponent(status=HealthStatus.unhealthy, error="timeout"))
        crawler = self._result(crawler_task, CrawlerComponent(status=HealthStatus.degraded, detail="timeout"))
        return DetailedHealthResponse(
            status=aggregate(db.status, crawler.status),
            checked_at=datetime.now(timezone.utc),
            components=Components(database=db, crawler=crawler),
        )

    @staticmethod
    def _result(task: "asyncio.Future", fallback):
        if task.cancelled() or not task.done():
            return fallback
        if task.exception() is not None:
            log_event(log, logging.ERROR, "component check crashed", exc_type=type(task.exception()).__name__)
            return fallback
        return task.result()

    async def check_cached(self, max_age_seconds: float = 1.0) -> DetailedHealthResponse:
        """Share one computation between many real-time monitor connections."""
        async with self._lock:
            now = time.monotonic()
            if self._last and now - self._last[0] < max_age_seconds:
                return self._last[1]
            report = await self.check()
            self._last = (time.monotonic(), report)
            return report
