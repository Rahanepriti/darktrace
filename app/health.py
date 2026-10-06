import asyncio
from datetime import datetime, timezone

from app.database import check_database_health
from app.redis_cache import HeartbeatCache
from app.config import settings


async def check_crawler_health() -> dict:
    """
    Check the latest crawler heartbeats stored in Redis.
    """

    cache = HeartbeatCache()

    try:
        heartbeats = await asyncio.wait_for(
            cache.get_all_heartbeats(),
            timeout=1.0,
        )

        if not heartbeats:
            return {
                "status": "unhealthy",
                "last_heartbeat": None,
                "active_workers": 0,
                "queue_depth": 0,
            }

        now = datetime.now(timezone.utc)

        latest = max(
            heartbeats,
            key=lambda heartbeat: heartbeat["timestamp"],
        )

        latest_timestamp = datetime.fromisoformat(
            latest["timestamp"].replace("Z", "+00:00")
        )

        age_seconds = (
            now - latest_timestamp
        ).total_seconds()

        total_queue_depth = sum(
            heartbeat["queue_depth"]
            for heartbeat in heartbeats
        )

        active_workers = len(heartbeats)

        if age_seconds > settings.crawler_heartbeat_max_age:
            crawler_status = "degraded"
        elif any(
            heartbeat["status"] == "degraded"
            for heartbeat in heartbeats
        ):
            crawler_status = "degraded"
        elif any(
            heartbeat["status"] == "down"
            for heartbeat in heartbeats
        ):
            crawler_status = "degraded"
        else:
            crawler_status = "healthy"

        return {
            "status": crawler_status,
            "last_heartbeat": latest_timestamp,
            "active_workers": active_workers,
            "queue_depth": total_queue_depth,
        }

    except asyncio.TimeoutError:
        return {
            "status": "degraded",
            "last_heartbeat": None,
            "active_workers": 0,
            "queue_depth": 0,
        }

    except Exception:
        return {
            "status": "degraded",
            "last_heartbeat": None,
            "active_workers": 0,
            "queue_depth": 0,
        }

    finally:
        await cache.close()


async def get_health() -> dict:
    """
    Build the complete system health response.
    """

    database = await check_database_health()
    crawler = await check_crawler_health()

    if database["status"] == "unhealthy":
        overall_status = "unhealthy"
    elif crawler["status"] == "unhealthy":
        overall_status = "unhealthy"
    elif (
        database["status"] == "degraded"
        or crawler["status"] == "degraded"
    ):
        overall_status = "degraded"
    else:
        overall_status = "healthy"

    return {
        "status": overall_status,
        "checked_at": datetime.now(timezone.utc),
        "components": {
            "database": database,
            "crawler": crawler,
        },
    }
