import asyncio
import base64
import os
import secrets
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis

from app.cache.redis_cache import HeartbeatCache
from app.core.config import Settings
from app.crypto.aes_gcm import CryptoService, KeyRing
from app.main import build_container, create_app
from app.schemas.health import DatabaseComponent, Heartbeat, HealthStatus, WorkerStatus
from app.services.health_service import HealthService
from app.services.heartbeat_processor import HeartbeatProcessor

API_TOKEN = secrets.token_urlsafe(24)
CRAWLER_TOKEN = secrets.token_urlsafe(24)


def random_key() -> bytes:
    return os.urandom(32)


def b64(key: bytes) -> str:
    return base64.urlsafe_b64encode(key).decode()


class StaticKeyProvider:
    def __init__(self, ring: KeyRing):
        self.ring = ring

    def load(self) -> KeyRing:
        return self.ring


def make_settings(key: bytes | None = None, **over) -> Settings:
    base = dict(
        app_env="test",
        health_encryption_key=b64(key or random_key()),
        active_key_version=1,
        health_api_token=API_TOKEN,
        crawler_ws_token=CRAWLER_TOKEN,
        database_url="",
        heartbeat_interval_seconds=20,
        heartbeat_ttl_seconds=40,
        monitor_push_interval_seconds=0.5,
    )
    base.update(over)
    return Settings(_env_file=None, **base)


def make_heartbeat(worker_id="cw-1", status=WorkerStatus.healthy, age=0, queue_depth=5) -> Heartbeat:
    ts = datetime.now(timezone.utc) - timedelta(seconds=age)
    return Heartbeat(worker_id=worker_id, status=status, timestamp=ts, queue_depth=queue_depth,
                     last_successful_fetch=ts - timedelta(seconds=10))


def hb_payload(worker_id="cw-1", age=0, **extra) -> dict:
    ts = datetime.now(timezone.utc) - timedelta(seconds=age)
    d = {"worker_id": worker_id, "status": "healthy",
         "timestamp": ts.isoformat().replace("+00:00", "Z"), "queue_depth": 3,
         "last_successful_fetch": ts.isoformat().replace("+00:00", "Z")}
    d.update(extra)
    return d


class StubDb:
    """Callable DB check with controllable outcome."""

    def __init__(self, status=HealthStatus.healthy, latency=5, error=None, delay=0.0):
        self.status, self.latency, self.error, self.delay = status, latency, error, delay

    async def __call__(self):
        if self.delay:
            await asyncio.sleep(self.delay)
        return DatabaseComponent(status=self.status, latency_ms=self.latency, error=self.error)


@pytest.fixture
def settings():
    return make_settings()


@pytest.fixture
def crypto(settings):
    return CryptoService(StaticKeyProvider(KeyRing({1: base64.urlsafe_b64decode(settings.health_encryption_key)}, 1)))


@pytest_asyncio.fixture
async def redis():
    r = FakeAsyncRedis(decode_responses=True)
    yield r
    await r.aclose()


@pytest.fixture
def cache(redis, settings):
    return HeartbeatCache(redis, settings.heartbeat_ttl, settings.redis_timeout_seconds,
                          settings.crawler_forget_after_seconds)


@pytest_asyncio.fixture
async def api(settings, cache, redis):
    """httpx client wired to the app with fake Redis and a stub DB check (no lifespan needed)."""
    db = StubDb()
    app = create_app(settings=settings)
    container = build_container(settings, redis_factory=lambda: redis, engine_factory=lambda: None)
    container.health_service = HealthService(settings, cache, db)
    container.cache = cache
    container.processor = HeartbeatProcessor(container.crypto, cache, settings)
    app.state.container = container
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        client.db = db
        client.container = container
        client.hdr = {"Authorization": f"Bearer {API_TOKEN}"}
        yield client
