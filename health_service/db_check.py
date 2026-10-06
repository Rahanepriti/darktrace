from __future__ import annotations

import asyncio
import logging
import time

import asyncpg

from .schemas import DatabaseComponent

logger = logging.getLogger("health_service.db_check")


async def check_database(dsn: str, timeout_seconds: float) -> DatabaseComponent:
    start = time.monotonic()
    try:
        conn = await asyncio.wait_for(asyncpg.connect(dsn), timeout=timeout_seconds)
    except Exception:
        logger.warning("health.database.connect_failed", exc_info=True)
        return DatabaseComponent(status="unhealthy", latency_ms=round((time.monotonic() - start) * 1000, 2))

    try:
        await asyncio.wait_for(conn.execute("SELECT 1"), timeout=timeout_seconds)
    except Exception:
        logger.warning("health.database.query_failed", exc_info=True)
        return DatabaseComponent(status="unhealthy", latency_ms=round((time.monotonic() - start) * 1000, 2))
    finally:
        await conn.close()

    latency_ms = round((time.monotonic() - start) * 1000, 2)
    return DatabaseComponent(status="healthy", latency_ms=latency_ms)
