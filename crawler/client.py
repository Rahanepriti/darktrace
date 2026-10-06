import asyncio
import json
from datetime import datetime, timezone

import websockets

from app.config import settings
from app.crypto import encrypt_message


API_WS_URL = "ws://127.0.0.1:8000/api/v1/ws/health"


async def send_heartbeat(websocket, worker_id: str):
    payload = {
        "worker_id": worker_id,
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "queue_depth": 14,
        "last_successful_fetch": datetime.now(timezone.utc).isoformat(),
    }

    message = json.dumps(payload)

    encrypted_message = encrypt_message(message)

    await websocket.send(encrypted_message)

    print(f"Heartbeat sent: {worker_id}")


async def run_crawler(worker_id: str = "cw-01"):
    while True:
        try:
            print(f"Connecting to {API_WS_URL}...")

            async with websockets.connect(API_WS_URL) as websocket:
                print("Connected to health WebSocket")

                while True:
                    await send_heartbeat(websocket, worker_id)

                    await asyncio.sleep(
                        settings.crawler_heartbeat_interval
                    )

        except Exception as exc:
            print(
                f"WebSocket connection failed: "
                f"{type(exc).__name__}: {exc}"
            )

            print("Retrying in 5 seconds...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(run_crawler())
