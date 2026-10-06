from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HeartbeatPayload(BaseModel):
    worker_id: str
    status: Literal["healthy", "degraded", "down"]
    timestamp: datetime
    queue_depth: int = Field(ge=0)
    last_successful_fetch: Optional[datetime] = None


class DatabaseComponent(BaseModel):
    status: Literal["healthy", "unhealthy"]
    latency_ms: Optional[float] = None


class CrawlerComponent(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    last_heartbeat: Optional[datetime] = None
    active_workers: int = 0
    queue_depth: int = 0


class ComponentsBlock(BaseModel):
    database: DatabaseComponent
    crawler: CrawlerComponent


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    checked_at: datetime
    components: ComponentsBlock


class MinimalHealthResponse(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    checked_at: datetime
