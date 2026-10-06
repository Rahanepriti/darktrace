from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

import websockets
from websockets.exceptions import ConnectionClosed

from ..crypto import encrypt_message
from ..schemas import HeartbeatPayload, utcnow

logger = logging.getLogger("health_service.crawler_client")

StatusProvider = Callable[[], Awaitable[dict]]


async def default_status_provider() -> dict:
    return {"status": "healthy", "queue_depth": 0, "last_successful_fetch": None}


async def build_heartbeat_payload(worker_id: str, status_provider: StatusProvider) -> HeartbeatPayload:
    snapshot = await status_provider()
    return HeartbeatPayload(
        worker_id=worker_id,
        status=snapshot["status"],
        timestamp=utcnow(),
        queue_depth=snapshot["queue_depth"],
        last_successful_fetch=snapshot.get("last_successful_fetch"),
    )


async def run_heartbeat_client(
    websocket_url: str,
    worker_id: str,
    key: bytes,
    key_version: str,
    interval_seconds: int,
    reconnect_backoff_seconds: float,
    status_provider: StatusProvider = default_status_provider,
    max_iterations: Optional[int] = None,
) -> None:
    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        try:
            async with websockets.connect(websocket_url) as connection:
                while max_iterations is None or iterations < max_iterations:
                    payload = await build_heartbeat_payload(worker_id, status_provider)
                    envelope = encrypt_message(payload.model_dump_json().encode("utf-8"), key, key_version)
                    await connection.send(envelope)
                    iterations += 1
                    await asyncio.sleep(interval_seconds)
        except (ConnectionClosed, OSError):
            logger.warning("health.crawler_client.disconnected", extra={"worker_id": worker_id})
            await asyncio.sleep(reconnect_backoff_seconds)
