from __future__ import annotations

from typing import Literal

from .schemas import CrawlerComponent, DatabaseComponent

OverallStatus = Literal["healthy", "degraded", "unhealthy"]


def combine_overall_status(database: DatabaseComponent, crawler: CrawlerComponent) -> OverallStatus:
    if database.status == "unhealthy" or crawler.status == "unhealthy":
        return "unhealthy"
    if crawler.status == "degraded":
        return "degraded"
    return "healthy"
