import json
import logging
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.config import settings
from app.crypto import decrypt_message
from app.redis_cache import HeartbeatCache
from app.schemas import CrawlerHeartbeat

logger = logging.getLogger(__name__)


async def crawler_health_websocket(websocket: WebSocket):
    """
    Receive encrypted crawler heartbeat messages over WebSocket.
    """

    await websocket.accept()

    cache = HeartbeatCache()

    try:
        while True:
            encrypted_message = await websocket.receive_text()

            try:
                decrypted_message = decrypt_message(encrypted_message)

                payload = json.loads(decrypted_message)

                heartbeat = CrawlerHeartbeat.model_validate(payload)

                now = datetime.now(timezone.utc)

                heartbeat_age = (
                    now - heartbeat.timestamp
                ).total_seconds()

                if heartbeat_age > settings.crawler_heartbeat_max_age:
                   logger.warning(
                       "Rejected stale crawler heartbeat from worker %s",
                    heartbeat.worker_id,
                   )
                   continue                

                await cache.set_heartbeat(
                    heartbeat.model_dump(mode="json")
                )

                logger.info(
                    "Heartbeat received from worker %s",
                    heartbeat.worker_id,
                )

            except (ValueError, json.JSONDecodeError, ValidationError) as exc:
                logger.warning(
                    "Rejected invalid crawler heartbeat: %s",
                    type(exc).__name__,
                )

                continue

    except WebSocketDisconnect:
        logger.info("Crawler WebSocket disconnected")

    finally:
        await cache.close()
