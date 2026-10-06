from datetime import datetime, timedelta, timezone

from health_service.crawler_health import aggregate_crawler_status, classify_worker
from health_service.schemas import HeartbeatPayload


def _heartbeat(worker_id: str, status: str, age_seconds: int, now: datetime, queue_depth: int = 5) -> HeartbeatPayload:
    return HeartbeatPayload(
        worker_id=worker_id,
        status=status,
        timestamp=now - timedelta(seconds=age_seconds),
        queue_depth=queue_depth,
    )


def test_fresh_healthy_worker_classifies_healthy():
    now = datetime.now(timezone.utc)
    entry = _heartbeat("cw-1", "healthy", age_seconds=5, now=now)
    assert classify_worker(entry, now, freshness_seconds=30) == "healthy"


def test_stale_worker_classifies_degraded_not_down():
    now = datetime.now(timezone.utc)
    entry = _heartbeat("cw-1", "healthy", age_seconds=120, now=now)
    assert classify_worker(entry, now, freshness_seconds=30) == "degraded"


def test_self_reported_down_worker_classifies_degraded():
    now = datetime.now(timezone.utc)
    entry = _heartbeat("cw-1", "down", age_seconds=5, now=now)
    assert classify_worker(entry, now, freshness_seconds=30) == "degraded"


def test_no_heartbeats_at_all_is_unhealthy():
    now = datetime.now(timezone.utc)
    component = aggregate_crawler_status([], now, freshness_seconds=30)
    assert component.status == "unhealthy"
    assert component.active_workers == 0
    assert component.last_heartbeat is None


def test_all_fresh_healthy_workers_aggregate_to_healthy():
    now = datetime.now(timezone.utc)
    entries = [
        _heartbeat("cw-1", "healthy", age_seconds=5, now=now, queue_depth=4),
        _heartbeat("cw-2", "healthy", age_seconds=8, now=now, queue_depth=6),
    ]
    component = aggregate_crawler_status(entries, now, freshness_seconds=30)
    assert component.status == "healthy"
    assert component.active_workers == 2
    assert component.queue_depth == 10


def test_one_stale_worker_degrades_overall_aggregate():
    now = datetime.now(timezone.utc)
    entries = [
        _heartbeat("cw-1", "healthy", age_seconds=5, now=now),
        _heartbeat("cw-2", "healthy", age_seconds=180, now=now),
    ]
    component = aggregate_crawler_status(entries, now, freshness_seconds=30)
    assert component.status == "degraded"


def test_active_workers_excludes_self_reported_down():
    now = datetime.now(timezone.utc)
    entries = [
        _heartbeat("cw-1", "healthy", age_seconds=5, now=now),
        _heartbeat("cw-2", "down", age_seconds=5, now=now),
    ]
    component = aggregate_crawler_status(entries, now, freshness_seconds=30)
    assert component.active_workers == 1


def test_last_heartbeat_reflects_most_recent_worker():
    now = datetime.now(timezone.utc)
    entries = [
        _heartbeat("cw-1", "healthy", age_seconds=50, now=now),
        _heartbeat("cw-2", "healthy", age_seconds=5, now=now),
    ]
    component = aggregate_crawler_status(entries, now, freshness_seconds=120)
    assert component.last_heartbeat == entries[1].timestamp
