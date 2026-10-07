"""
Database connectivity check for GET /api/v1/health.

Runs a trivial query (SELECT 1) against DATABASE_URL with a timeout --
we don't want a hung DB to hang the whole health endpoint. If
DATABASE_URL isn't configured at all, it will say so explicitly rather than
pretending the DB is healthy.
"""
import asyncio
import time

from config import DATABASE_URL, DB_CHECK_TIMEOUT_SECONDS


async def check_database() -> dict:
    if not DATABASE_URL:
        return {"ok": False, "detail": "DATABASE_URL not configured"}

    start = time.monotonic()
    try:
        await asyncio.wait_for(_run_select_1(), timeout=DB_CHECK_TIMEOUT_SECONDS)
        elapsed_ms = round((time.monotonic() - start) * 1000, 1)
        return {"ok": True, "detail": "connected", "latency_ms": elapsed_ms}
    except asyncio.TimeoutError:
        return {"ok": False, "detail": f"timed out after {DB_CHECK_TIMEOUT_SECONDS}s"}
    except Exception as exc:
        return {"ok": False, "detail": f"connection error: {exc}"}


async def _run_select_1() -> None:
    """Isolated so check_database() can wrap it in a timeout cleanly.
    Uses asyncpg directly -- lightweight, no ORM needed for a single
    SELECT 1 probe."""
    import asyncpg  # imported lazily so this file doesn't hard-require
                     # asyncpg if the DB check is never actually used

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.fetchval("SELECT 1")
    finally:
        await conn.close()
