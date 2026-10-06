import time

import asyncpg

from app.config import settings


async def check_database_health() -> dict:
    """
    Check PostgreSQL connectivity and measure query latency.
    """

    start = time.perf_counter()

    try:
        connection = await asyncpg.connect(
            dsn=settings.database_url,
            timeout=1.0,
        )

        try:
            await connection.fetchval("SELECT 1")
        finally:
            await connection.close()

        latency_ms = round((time.perf_counter() - start) * 1000, 2)

        return {
            "status": "healthy",
            "latency_ms": latency_ms,
        }

    except Exception:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)

        return {
            "status": "unhealthy",
            "latency_ms": latency_ms,
        }
