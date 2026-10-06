"""CyArt DarkTrace - Health Monitoring Module (FastAPI application factory)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Callable

from fastapi import FastAPI
from redis import asyncio as aioredis

from app.api import dashboard, health, websocket
from app.cache.redis_cache import HeartbeatCache
from app.core.config import Settings, get_settings
from app.core.container import Container
from app.core.logging import configure_logging, get_logger, log_event
from app.core.security import build_key_provider
from app.crypto.aes_gcm import CryptoService, KeyProvider
from app.services.database_health import build_engine, check_database
from app.services.health_service import HealthService
from app.services.heartbeat_processor import HeartbeatProcessor

log = get_logger("main")


def build_container(
    settings: Settings,
    redis_factory: Callable[[], Any] | None = None,
    engine_factory: Callable[[], Any] | None = None,
    key_provider: KeyProvider | None = None,
) -> Container:
    crypto = CryptoService(key_provider or build_key_provider(settings), settings.key_refresh_seconds)  # fails fast
    if redis_factory:
        redis = redis_factory()
    else:
        redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=settings.redis_timeout_seconds,
            socket_timeout=settings.redis_timeout_seconds,
        )
    if engine_factory:
        engine = engine_factory()
    else:
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is not set")
        engine = build_engine(settings.database_url, settings.database_timeout_seconds)

    cache = HeartbeatCache(redis, settings.heartbeat_ttl, settings.redis_timeout_seconds,
                           settings.crawler_forget_after_seconds)

    async def db_check():
        return await check_database(engine, settings.database_timeout_seconds, settings.database_degraded_latency_ms)

    return Container(
        settings=settings, crypto=crypto, cache=cache,
        processor=HeartbeatProcessor(crypto, cache, settings),
        health_service=HealthService(settings, cache, db_check),
        redis=redis, engine=engine,
    )


def create_app(
    settings: Settings | None = None,
    redis_factory: Callable[[], Any] | None = None,
    engine_factory: Callable[[], Any] | None = None,
    key_provider: KeyProvider | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        s = settings or get_settings()
        configure_logging(s.log_level)
        if getattr(app.state, "container", None) is None:  # tests may pre-inject one
            app.state.container = build_container(s, redis_factory, engine_factory, key_provider)
        c: Container = app.state.container
        log_event(log, logging.INFO, "health monitoring started", env=s.app_env,
                  key_versions=c.crypto.versions, active_key_version=c.crypto.active_version,
                  public_health=s.public_health_endpoint)
        if not s.crawler_ws_token or not s.health_api_token:
            log_event(log, logging.WARNING, "CRAWLER_WS_TOKEN / HEALTH_API_TOKEN not set: related endpoints will reject all callers")
        yield
        if c.redis is not None:
            await c.redis.aclose()
        if c.engine is not None:
            await c.engine.dispose()

    app = FastAPI(title="CyArt DarkTrace Health Monitoring", version="1.0.0", lifespan=lifespan,
                  docs_url=None if (settings and settings.app_env == "production") else "/docs", redoc_url=None)
    app.include_router(health.router)
    app.include_router(websocket.router)
    app.include_router(dashboard.router)

    route_env = settings.app_env if settings else "development"

    @app.get("/", tags=["system"])
    async def root() -> dict[str, str]:
        return {
            "name": "CyArt DarkTrace Health Monitoring",
            "status": "ok",
            "version": "1.0.0",
            "docs": "/docs" if route_env != "production" else "disabled",
            "health": "/health",
            "api_health": "/api/v1/health",
            "dashboard": "/dashboard",
        }

    @app.get("/health", tags=["system"])
    async def root_health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
