"""
FastAPI app: mounts the WebSocket heartbeat receiver and exposes
GET /api/v1/health, which combines DB connectivity + crawler heartbeat
status (read from Redis) into one overall status.

Run: uvicorn main:app --host 0.0.0.0 --port 8001 --reload
"""
import time

from fastapi import FastAPI

from ws_server import router as ws_router
from db_check import check_database
from redis_cache import get_all_crawler_statuses
from config import HEARTBEAT_STALE_AFTER_SECONDS

app = FastAPI(title="DarkTrace Health Check Service")
app.include_router(ws_router)


def _crawler_summary() -> dict:
    """Reads every known crawler's last status from Redis and buckets
    each one into ok / stale / down / error, using the reported
    timestamp (not just key presence) to catch a crawler that's still
    inside its TTL window but hasn't sent anything in a while."""
    statuses = get_all_crawler_statuses()
    now = time.time()

    summary = {}
    for crawler_id, status in statuses.items():
        if status is None:
            summary[crawler_id] = "down"  # Redis key expired entirely
            continue

        age = now - status["reported_ts"]
        if age > HEARTBEAT_STALE_AFTER_SECONDS:
            summary[crawler_id] = "stale"
        elif status["status"] == "error":
            summary[crawler_id] = "error"
        elif status["status"] == "degraded":
            summary[crawler_id] = "degraded"
        else:
            summary[crawler_id] = "ok"

    return summary


def _overall_status(db_ok: bool, crawler_summary: dict) -> str:
    """Combines DB + crawler results into one of: healthy, degraded,
    unhealthy.

    - unhealthy: DB is down. The API can't do its job without the DB,
      regardless of crawler state.
    - degraded: DB is fine, but at least one crawler is not fully "ok"
      (stale, down, degraded, or error).
    - healthy: DB is fine AND every known crawler is reporting "ok".

    NOTE: confirm this exact mapping with your team lead -- the spec
    leaves the precise condition table as an open question (see the
    README). This is the most defensible default in the meantime.
    """
    if not db_ok:
        return "unhealthy"

    if not crawler_summary:
        # No crawlers have ever reported in -- can't claim "healthy"
        # when we have zero visibility into the crawler fleet.
        return "degraded"

    if all(state == "ok" for state in crawler_summary.values()):
        return "healthy"

    return "degraded"


@app.get("/api/v1/health")
async def health():
    db_result = await check_database()
    crawler_summary = _crawler_summary()
    overall = _overall_status(db_result["ok"], crawler_summary)

    return {
        "status": overall,
        "checked_at": time.time(),
        "database": db_result,
        "crawlers": crawler_summary,
    }
