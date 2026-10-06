"""Pydantic models for heartbeats and health responses."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class HealthStatus(str, Enum):
    healthy = "healthy"
    degraded = "degraded"
    unhealthy = "unhealthy"


class WorkerStatus(str, Enum):
    healthy = "healthy"
    degraded = "degraded"
    down = "down"


class Heartbeat(BaseModel):
    """Payload the crawler sends (inside the AES-GCM envelope)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    worker_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    status: WorkerStatus
    timestamp: AwareDatetime
    queue_depth: int = Field(ge=0, le=1_000_000_000)
    last_successful_fetch: AwareDatetime | None = None

    @field_validator("timestamp", "last_successful_fetch")
    @classmethod
    def _to_utc(cls, v: datetime | None) -> datetime | None:
        return v.astimezone(timezone.utc) if v else v


class DatabaseComponent(BaseModel):
    status: HealthStatus
    latency_ms: int | None = None
    error: str | None = None  # generic code only (e.g. "timeout"); never DSNs/messages


class WorkerView(BaseModel):
    worker_id: str
    status: Literal["healthy", "degraded", "down", "stale"]
    last_heartbeat: datetime | None = None
    queue_depth: int | None = None
    last_successful_fetch: datetime | None = None


class CrawlerComponent(BaseModel):
    status: HealthStatus
    last_heartbeat: datetime | None = None
    active_workers: int = 0
    queue_depth: int = 0
    stale_workers: int = 0
    workers: list[WorkerView] = Field(default_factory=list)
    detail: str | None = None


class Components(BaseModel):
    database: DatabaseComponent
    crawler: CrawlerComponent


class DetailedHealthResponse(BaseModel):
    status: HealthStatus
    checked_at: datetime
    components: Components


class PublicHealthResponse(BaseModel):
    status: HealthStatus
