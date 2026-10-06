from __future__ import annotations

from datetime import datetime
from typing import List, Literal

from .cache import HeartbeatCache
from .schemas import CrawlerComponent, HeartbeatPayload

WorkerClassification = Literal["healthy", "degraded"]


def classify_worker(entry: HeartbeatPayload, now: datetime, freshness_seconds: int) -> WorkerClassification:
    age_seconds = (now - entry.timestamp).total_seconds()
    if age_seconds > freshness_seconds:
        return "degraded"
    if entry.status in ("degraded", "down"):
        return "degraded"
    return "healthy"


def aggregate_crawler_status(
    entries: List[HeartbeatPayload],
    now: datetime,
    freshness_seconds: int,
) -> CrawlerComponent:
    if not entries:
        return CrawlerComponent(status="unhealthy", last_heartbeat=None, active_workers=0, queue_depth=0)

    classifications = [classify_worker(entry, now, freshness_seconds) for entry in entries]
    overall = "healthy" if all(c == "healthy" for c in classifications) else "degraded"
    active_workers = sum(1 for entry in entries if entry.status != "down")
    queue_depth = sum(entry.queue_depth for entry in entries)
    last_heartbeat = max(entry.timestamp for entry in entries)

    return CrawlerComponent(
        status=overall,
        last_heartbeat=last_heartbeat,
        active_workers=active_workers,
        queue_depth=queue_depth,
    )


async def get_crawler_component(cache: HeartbeatCache, now: datetime, freshness_seconds: int) -> CrawlerComponent:
    entries = await cache.get_all_heartbeats()
    return aggregate_crawler_status(entries, now, freshness_seconds)
