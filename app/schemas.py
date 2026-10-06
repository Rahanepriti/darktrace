from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CrawlerHeartbeat(BaseModel):
    worker_id: str = Field(min_length=1)
    status: Literal["healthy", "degraded", "down"]
    timestamp: datetime
    queue_depth: int = Field(ge=0)
    last_successful_fetch: datetime
