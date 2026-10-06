"""Lightweight PostgreSQL health check (SELECT 1) with a hard timeout."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.logging import get_logger, log_event
from app.schemas.health import DatabaseComponent, HealthStatus

log = get_logger("database_health")


def normalize_database_url(url: str) -> str:
    """Accept postgres:// and postgresql:// and force the asyncpg driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


def build_engine(url: str, timeout_seconds: float) -> AsyncEngine:
    url = normalize_database_url(url)
    if url.startswith("postgresql+asyncpg://"):
        return create_async_engine(
            url,
            pool_size=3,
            max_overflow=2,
            pool_timeout=timeout_seconds,
            connect_args={"timeout": timeout_seconds, "command_timeout": timeout_seconds},
        )
    return create_async_engine(url)  # e.g. sqlite+aiosqlite for tests


async def check_database(engine: Any, timeout_seconds: float, degraded_latency_ms: int = 500) -> DatabaseComponent:
    start = time.perf_counter()

    async def _query() -> None:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    def elapsed_ms() -> int:
        return int((time.perf_counter() - start) * 1000)

    try:
        await asyncio.wait_for(_query(), timeout_seconds)
    except asyncio.TimeoutError:
        log_event(log, logging.ERROR, "database health failure", reason="timeout")
        return DatabaseComponent(status=HealthStatus.unhealthy, latency_ms=elapsed_ms(), error="timeout")
    except Exception as exc:  # log the type only: driver messages can embed DSNs
        log_event(log, logging.ERROR, "database health failure", reason="unreachable", exc_type=type(exc).__name__)
        return DatabaseComponent(status=HealthStatus.unhealthy, latency_ms=None, error="unreachable")

    latency = elapsed_ms()
    status = HealthStatus.degraded if latency > degraded_latency_ms else HealthStatus.healthy
    return DatabaseComponent(status=status, latency_ms=latency, error="slow_response" if status != HealthStatus.healthy else None)
