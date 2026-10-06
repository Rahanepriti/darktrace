import pytest

from app.redis_cache import HeartbeatCache


@pytest.mark.asyncio
async def test_store_and_get_heartbeat():
    cache = HeartbeatCache()

    heartbeat = {
        "worker_id": "cw-test-01",
        "status": "healthy",
        "timestamp": "2026-10-06T14:00:00Z",
        "queue_depth": 14,
        "last_successful_fetch": "2026-10-06T13:59:50Z",
    }

    await cache.set_heartbeat(heartbeat)

    result = await cache.get_heartbeat("cw-test-01")

    assert result == heartbeat

    await cache.delete_heartbeat("cw-test-01")
    await cache.close()


@pytest.mark.asyncio
async def test_missing_heartbeat_returns_none():
    cache = HeartbeatCache()

    result = await cache.get_heartbeat("cw-nonexistent")

    assert result is None

    await cache.close()


@pytest.mark.asyncio
async def test_get_all_heartbeats():
    cache = HeartbeatCache()

    heartbeat = {
        "worker_id": "cw-test-02",
        "status": "healthy",
        "timestamp": "2026-10-06T14:00:00Z",
        "queue_depth": 5,
        "last_successful_fetch": "2026-10-06T13:59:55Z",
    }

    await cache.set_heartbeat(heartbeat)

    results = await cache.get_all_heartbeats()

    assert any(
        item["worker_id"] == "cw-test-02"
        for item in results
    )

    await cache.delete_heartbeat("cw-test-02")
    await cache.close()
