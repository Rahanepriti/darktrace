"""Crawler status derived from the Redis heartbeat snapshot.

Rules (see README "Health status logic"):
  * no heartbeat ever seen                          -> unhealthy ("no_heartbeat_received")
  * every known worker stale, newest <= threshold   -> degraded  ("heartbeat_stale")   [NOT "crashed"]
  * every known worker stale, newest >  threshold   -> unhealthy ("no_heartbeat_within_window")
  * some fresh, but any stale / degraded / down     -> degraded
  * all fresh workers healthy                       -> healthy
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.cache.redis_cache import CacheSnapshot, CacheUnavailable, HeartbeatCache
from app.core.logging import get_logger, log_event
from app.schemas.health import CrawlerComponent, HealthStatus, WorkerStatus, WorkerView

log = get_logger("crawler_health")


def evaluate_crawler(snap: CacheSnapshot, now: datetime, unhealthy_after_seconds: int) -> CrawlerComponent:
    fresh = {h.worker_id: h for h in snap.fresh}
    stale_ids = sorted(w for w in snap.last_seen if w not in fresh)

    workers = [
        WorkerView(
            worker_id=h.worker_id,
            status=h.status.value,
            last_heartbeat=h.timestamp,
            queue_depth=h.queue_depth,
            last_successful_fetch=h.last_successful_fetch,
        )
        for h in sorted(fresh.values(), key=lambda x: x.worker_id)
    ] + [WorkerView(worker_id=w, status="stale", last_heartbeat=snap.last_seen[w]) for w in stale_ids]

    if not fresh and not snap.last_seen:
        return CrawlerComponent(status=HealthStatus.unhealthy, detail="no_heartbeat_received")

    if not fresh:
        newest = max(snap.last_seen.values())
        age = (now - newest).total_seconds()
        log_event(log, logging.WARNING, "heartbeat stale", workers=len(stale_ids), age_seconds=int(age))
        if age > unhealthy_after_seconds:
            status, detail = HealthStatus.unhealthy, "no_heartbeat_within_window"
        else:
            status, detail = HealthStatus.degraded, "heartbeat_stale"
        return CrawlerComponent(
            status=status, last_heartbeat=newest, stale_workers=len(stale_ids), workers=workers, detail=detail
        )

    active = [h for h in fresh.values() if h.status != WorkerStatus.down]
    detail = None
    status = HealthStatus.healthy
    if stale_ids:
        status, detail = HealthStatus.degraded, "some_workers_stale"
        log_event(log, logging.WARNING, "heartbeat stale", workers=len(stale_ids))
    if any(h.status != WorkerStatus.healthy for h in fresh.values()):
        status, detail = HealthStatus.degraded, detail or "some_workers_unhealthy"
    if not active:
        status, detail = HealthStatus.degraded, "all_workers_down"
    return CrawlerComponent(
        status=status,
        last_heartbeat=max(h.timestamp for h in fresh.values()),
        active_workers=len(active),
        queue_depth=sum(h.queue_depth for h in fresh.values()),
        stale_workers=len(stale_ids),
        workers=workers,
        detail=detail,
    )


async def check_crawler(cache: HeartbeatCache, unhealthy_after_seconds: int) -> CrawlerComponent:
    try:
        snap = await cache.snapshot()
    except CacheUnavailable as exc:
        # Cannot determine crawler state: degraded (we are blind), not unhealthy (DB may be fine).
        log_event(log, logging.ERROR, "redis failure", reason=str(exc))
        return CrawlerComponent(status=HealthStatus.degraded, detail="cache_unavailable")
    return evaluate_crawler(snap, datetime.now(timezone.utc), unhealthy_after_seconds)
