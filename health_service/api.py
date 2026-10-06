from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

from fastapi import Depends, FastAPI, Header, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from redis.asyncio import Redis

from . import config
from .cache import HeartbeatCache, RedisHeartbeatCache
from .crawler_health import get_crawler_component
from .crypto import DecryptionError, decrypt_message
from .db_check import check_database
from .health import combine_overall_status
from .replay import is_replayed
from .schemas import DatabaseComponent, HeartbeatPayload, utcnow
from .secrets import EnvSecretProvider, build_key_resolver

logger = logging.getLogger("health_service.api")

_secret_provider = EnvSecretProvider(
    env_prefix=config.AES_KEY_ENV_PREFIX,
    active_version_env=config.ACTIVE_AES_KEY_VERSION_ENV,
    default_version=config.DEFAULT_AES_KEY_VERSION,
)
_key_resolver = build_key_resolver(_secret_provider)

_redis_client: Redis | None = None


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global _redis_client
    _redis_client = Redis.from_url(config.REDIS_URL)
    yield
    if _redis_client is not None:
        await _redis_client.aclose()


app = FastAPI(title="DarkTrace Health Monitoring Service", version="1.0.0", lifespan=lifespan)


def get_cache() -> HeartbeatCache:
    if _redis_client is None:
        raise RuntimeError("Redis client not initialized")
    return RedisHeartbeatCache(
        _redis_client, key_prefix=config.HEARTBEAT_CACHE_KEY_PREFIX, ttl_seconds=config.HEARTBEAT_TTL_SECONDS
    )


async def database_dependency() -> DatabaseComponent:
    return await check_database(config.DATABASE_DSN, config.DATABASE_CHECK_TIMEOUT_SECONDS)


async def crawler_dependency(cache: HeartbeatCache = Depends(get_cache)):
    return await get_crawler_component(cache, utcnow(), config.HEARTBEAT_FRESHNESS_SECONDS)


@app.get("/api/v1/health")
async def get_health(
    database: DatabaseComponent = Depends(database_dependency),
    crawler=Depends(crawler_dependency),
    x_api_key: str = Header(default=""),
) -> Dict[str, Any]:
    checked_at = utcnow()
    overall = combine_overall_status(database, crawler)

    if config.HEALTH_DETAILED_REQUIRES_AUTH and x_api_key != config.HEALTH_API_KEY:
        return {"status": overall, "checked_at": checked_at.isoformat()}

    return {
        "status": overall,
        "checked_at": checked_at.isoformat(),
        "components": {
            "database": database.model_dump(),
            "crawler": crawler.model_dump(mode="json"),
        },
    }


@app.websocket("/api/v1/ws/health")
async def websocket_health(websocket: WebSocket, cache: HeartbeatCache = Depends(get_cache)) -> None:
    await websocket.accept()
    try:
        while True:
            try:
                raw_message = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            try:
                plaintext = decrypt_message(raw_message, _key_resolver)
            except DecryptionError as exc:
                logger.warning("health.heartbeat.rejected", extra={"reason": str(exc)})
                continue

            try:
                payload = HeartbeatPayload.model_validate_json(plaintext)
            except ValidationError as exc:
                logger.warning("health.heartbeat.invalid_schema", extra={"reason": str(exc)})
                continue

            if is_replayed(payload.timestamp, utcnow(), config.REPLAY_WINDOW_SECONDS):
                logger.warning("health.heartbeat.replay_rejected", extra={"worker_id": payload.worker_id})
                continue

            try:
                await cache.record_heartbeat(payload)
            except Exception:
                logger.exception("health.heartbeat.cache_write_failed")
    except Exception:
        logger.exception("health.websocket.unexpected_error")
