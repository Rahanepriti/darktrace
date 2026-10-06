import asyncio
import time

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.cache.redis_cache import HeartbeatCache
from app.schemas.health import DetailedHealthResponse, HealthStatus, WorkerStatus
from app.services.database_health import check_database, normalize_database_url
from app.services.health_service import HealthService
from tests.conftest import StubDb, make_heartbeat, make_settings

URL = "/api/v1/health"


async def test_healthy_response_and_schema(api):
    await api.container.cache.store(make_heartbeat("cw-14", queue_depth=14))
    r = await api.get(URL, headers=api.hdr)
    assert r.status_code == 200
    body = r.json()
    DetailedHealthResponse.model_validate(body)  # schema holds
    assert body["status"] == "healthy"
    assert body["checked_at"].endswith("Z")
    assert body["components"]["database"] == {"status": "healthy", "latency_ms": 5}
    cr = body["components"]["crawler"]
    assert cr["active_workers"] == 1 and cr["queue_depth"] == 14 and cr["last_heartbeat"]
    assert r.headers["cache-control"] == "no-store"


async def test_degraded_when_worker_degraded(api):
    await api.container.cache.store(make_heartbeat("cw-1", status=WorkerStatus.degraded))
    r = await api.get(URL, headers=api.hdr)
    assert r.status_code == 200 and r.json()["status"] == "degraded"


async def test_degraded_when_db_slow(api):
    await api.container.cache.store(make_heartbeat())
    api.db.status, api.db.error = HealthStatus.degraded, "slow_response"
    assert (await api.get(URL, headers=api.hdr)).json()["status"] == "degraded"


async def test_unhealthy_when_database_down(api):
    await api.container.cache.store(make_heartbeat())
    api.db.status, api.db.latency, api.db.error = HealthStatus.unhealthy, None, "unreachable"
    r = await api.get(URL, headers=api.hdr)
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "unhealthy"
    assert body["components"]["database"] == {"status": "unhealthy", "error": "unreachable"}


async def test_unhealthy_when_no_crawler_heartbeat_ever(api):
    body = (await api.get(URL, headers=api.hdr)).json()
    assert body["status"] == "unhealthy"
    assert body["components"]["crawler"]["detail"] == "no_heartbeat_received"


# ---- access modes --------------------------------------------------------------------
async def test_unauthenticated_rejected_by_default(api):
    assert (await api.get(URL)).status_code == 401


async def test_wrong_token_rejected(api):
    assert (await api.get(URL, headers={"Authorization": "Bearer nope"})).status_code == 401


async def test_public_mode_returns_status_only(api, settings):
    settings.public_health_endpoint = True
    await api.container.cache.store(make_heartbeat())
    r = await api.get(URL)
    assert r.status_code == 200 and r.json() == {"status": "healthy"}
    assert "components" in (await api.get(URL, headers=api.hdr)).json()  # token still gets detail


# ---- database check ----------------------------------------------------------------
async def test_real_database_check_with_sqlite():
    engine = create_async_engine("sqlite+aiosqlite://")
    res = await check_database(engine, 1.0)
    assert res.status == HealthStatus.healthy and res.latency_ms is not None
    await engine.dispose()


async def test_database_error_does_not_leak_dsn():
    engine = create_async_engine("sqlite+aiosqlite:////nonexistent_dir/secret_password_db.sqlite")
    res = await check_database(engine, 1.0)
    assert res.status == HealthStatus.unhealthy
    assert "secret_password" not in res.model_dump_json() and "nonexistent" not in res.model_dump_json()
    await engine.dispose()


def test_url_normalization():
    assert normalize_database_url("postgres://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"
    assert normalize_database_url("postgresql://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"


# ---- performance / no-hang guarantees ------------------------------------------------
class HangingEngine:
    def connect(self):
        return self

    async def __aenter__(self):
        await asyncio.sleep(30)

    async def __aexit__(self, *a):
        return False


class DeadRedis:
    """Redis that is unreachable (raises) or black-holed (hangs)."""

    def __init__(self, hang=False):
        self.hang = hang

    async def _fail(self, *a, **k):
        if self.hang:
            await asyncio.sleep(30)
        from redis.exceptions import ConnectionError
        raise ConnectionError("down")

    hgetall = mget = hdel = ping = _fail


async def test_slow_postgres_does_not_hang_health():
    s = make_settings(database_timeout_seconds=0.2)

    async def db():
        return await check_database(HangingEngine(), s.database_timeout_seconds)

    cache = HeartbeatCache(DeadRedis(), 40, 0.2)
    hs = HealthService(s, cache, db)
    t = time.perf_counter()
    r = await hs.check()
    assert time.perf_counter() - t < 1.0
    assert r.components.database.status == HealthStatus.unhealthy and r.components.database.error == "timeout"


@pytest.mark.parametrize("hang", [False, True])
async def test_redis_unavailable_is_fast_and_degraded(hang):
    s = make_settings(redis_timeout_seconds=0.2)
    hs = HealthService(s, HeartbeatCache(DeadRedis(hang), 40, 0.2), StubDb())
    t = time.perf_counter()
    r = await hs.check()
    assert time.perf_counter() - t < 1.0
    assert r.components.crawler.status == HealthStatus.degraded and r.components.crawler.detail == "cache_unavailable"
    assert r.status == HealthStatus.degraded


async def test_overall_budget_enforced_even_if_checks_ignore_timeouts():
    s = make_settings(health_budget_seconds=0.3)
    hs = HealthService(s, HeartbeatCache(DeadRedis(), 40, 5), StubDb(delay=30))
    t = time.perf_counter()
    r = await hs.check()
    assert time.perf_counter() - t < 1.0
    assert r.status == HealthStatus.unhealthy and r.components.database.error == "timeout"


async def test_crawler_disappeared_completes_quickly(api, redis):
    from app.cache.redis_cache import HEARTBEAT_PREFIX
    await api.container.cache.store(make_heartbeat("cw-1"))
    await redis.delete(HEARTBEAT_PREFIX + "cw-1")
    t = time.perf_counter()
    r = await api.get(URL, headers=api.hdr)
    assert time.perf_counter() - t < 2.0 and r.json()["status"] == "degraded"
