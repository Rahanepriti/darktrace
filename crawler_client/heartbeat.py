import asyncio
from datetime import datetime, timezone

import websockets

from app.services.crawler_health import encrypt_message


API_WS_URL = "ws://127.0.0.1:8000/api/v1/ws/health"
WORKER_ID = "cw-test-01"


async def send_heartbeat():
    async with websockets.connect(API_WS_URL) as websocket:
        while True:
            heartbeat = {
                "worker_id": WORKER_ID,
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "queue_depth": 14,
                "last_successful_fetch": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            }

            encrypted_heartbeat = encrypt_message(heartbeat)

            await websocket.send(encrypted_heartbeat)

            print("Heartbeat sent")

            await asyncio.sleep(20)


asyncio.run(send_heartbeat())
