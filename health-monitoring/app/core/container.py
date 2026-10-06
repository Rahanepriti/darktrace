"""Dependency container stored on app.state (built in the lifespan; injectable in tests)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import Request, WebSocket

from app.cache.redis_cache import HeartbeatCache
from app.core.config import Settings
from app.crypto.aes_gcm import CryptoService
from app.services.health_service import HealthService
from app.services.heartbeat_processor import HeartbeatProcessor


@dataclass
class Container:
    settings: Settings
    crypto: CryptoService
    cache: HeartbeatCache
    processor: HeartbeatProcessor
    health_service: HealthService
    redis: Any = None
    engine: Any = None
    monitor_connections: int = field(default=0)


def get_container(conn: Request | WebSocket) -> Container:
    return conn.app.state.container
