import asyncio
from datetime import datetime, timedelta, timezone

from app.cache.redis_cache import CacheSnapshot, HEARTBEAT_PREFIX, HeartbeatCache
from app.schemas.health import HealthStatus, WorkerStatus
from app.services.crawler_health import evaluate_crawler
from tests.conftest import make_heartbeat

NOW = datetime.now(timezone.utc)


def test_no_heartbeat_ever_is_unhealthy():
    c = evaluate_crawler(CacheSnapshot(), NOW, 300)
    assert c.status == HealthStatus.unhealthy and c.detail == "no_heartbeat_received"


def test_recently_expired_heartbeat_is_degraded_not_crashed():
    snap = CacheSnapshot(fresh=[], last_seen={"cw-1": NOW - timedelta(seconds=60)})
    c = evaluate_crawler(snap, NOW, 300)
    assert c.status == HealthStatus.degraded and c.detail == "heartbeat_stale"
    assert c.stale_workers == 1 and c.workers[0].status == "stale"


def test_stale_beyond_window_is_unhealthy():
    snap = CacheSnapshot(fresh=[], last_seen={"cw-1": NOW - timedelta(seconds=301)})
    assert evaluate_crawler(snap, NOW, 300).status == HealthStatus.unhealthy


def test_one_stale_one_fresh_is_degraded():
    hb = make_heartbeat("cw-1")
    snap = CacheSnapshot(fresh=[hb], last_seen={"cw-1": NOW, "cw-2": NOW - timedelta(seconds=90)})
    c = evaluate_crawler(snap, NOW, 300)
    assert c.status == HealthStatus.degraded and c.active_workers == 1 and c.stale_workers == 1


def test_all_fresh_healthy():
    hbs = [make_heartbeat("cw-1", queue_depth=4), make_heartbeat("cw-2", queue_depth=6)]
    c = evaluate_crawler(CacheSnapshot(fresh=hbs, last_seen={h.worker_id: NOW for h in hbs}), NOW, 300)
    assert c.status == HealthStatus.healthy and c.queue_depth == 10 and c.active_workers == 2


def test_degraded_or_down_worker():
    hbs = [make_heartbeat("cw-1"), make_heartbeat("cw-2", status=WorkerStatus.down)]
    c = evaluate_crawler(CacheSnapshot(fresh=hbs, last_seen={h.worker_id: NOW for h in hbs}), NOW, 300)
    assert c.status == HealthStatus.degraded and c.active_workers == 1


async def test_redis_stores_heartbeat_per_worker(cache, redis):
    await cache.store(make_heartbeat("cw-14", queue_depth=14))
    raw = await redis.get(HEARTBEAT_PREFIX + "cw-14")
    assert '"worker_id":"cw-14"' in raw and '"queue_depth":14' in raw
    assert 0 < await redis.ttl(HEARTBEAT_PREFIX + "cw-14") <= 40


async def test_real_ttl_expiry_makes_worker_stale(redis):
    cache = HeartbeatCache(redis, ttl_seconds=1, timeout_seconds=1, forget_after_seconds=3600)
    await cache.store(make_heartbeat("cw-1"))
    snap = await cache.snapshot()
    assert [h.worker_id for h in snap.fresh] == ["cw-1"]
    await asyncio.sleep(1.3)  # TTL passes
    snap = await cache.snapshot()
    assert snap.fresh == [] and "cw-1" in snap.last_seen  # remembered => stale, not "never seen"
    assert evaluate_crawler(snap, datetime.now(timezone.utc), 300).status == HealthStatus.degraded


async def test_long_gone_worker_is_forgotten(redis):
    cache = HeartbeatCache(redis, ttl_seconds=1, timeout_seconds=1, forget_after_seconds=3600)
    await cache.store(make_heartbeat("cw-old"), received_at=NOW - timedelta(hours=2))
    assert (await cache.snapshot()).last_seen == {}


async def test_nonce_claim_is_single_use(cache):
    assert await cache.claim_nonce("ab12", 60) is True
    assert await cache.claim_nonce("ab12", 60) is False


async def test_health_reports_stale_after_expiry(api, redis):
    await api.container.cache.store(make_heartbeat("cw-1"))
    await redis.delete(HEARTBEAT_PREFIX + "cw-1")  # what TTL expiry does
    body = (await api.get("/api/v1/health", headers=api.hdr)).json()
    assert body["status"] == "degraded"
    assert body["components"]["crawler"]["detail"] == "heartbeat_stale"
