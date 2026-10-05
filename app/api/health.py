from datetime import datetime, timezone

from fastapi import APIRouter

from app.services.crawler_health import check_crawler_health
from app.services.database_health import check_database_health


router = APIRouter()


@router.get("/api/v1/health")
def health_check():
    database = check_database_health()
    crawler = check_crawler_health()

    if database["status"] == "unhealthy":
        overall_status = "unhealthy"
    elif crawler["status"] != "healthy":
        overall_status = "degraded"
    else:
        overall_status = "healthy"

    return {
        "status": overall_status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "components": {
            "database": database,
            "crawler": crawler,
        },
    }
