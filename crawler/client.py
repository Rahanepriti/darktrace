"""Outbound-only crawler heartbeat client for local integration testing."""
import asyncio
import json
import os
from datetime import datetime, timezone
import websockets
from app.crypto_utils import encrypt_json

WS_URL = os.getenv("HEALTH_WS_URL", "ws://127.0.0.1:8000/api/v1/ws/health")
WORKER_ID = os.getenv("WORKER_ID", "cw-local-01")
INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "20"))

async def main():
    async with websockets.connect(WS_URL, ping_interval=20, close_timeout=5) as ws:
        while True:
            now = datetime.now(timezone.utc)
            payload = {
                "worker_id": WORKER_ID,
                "status": os.getenv("WORKER_STATUS", "healthy"),
                "timestamp": now.isoformat().replace("+00:00", "Z"),
                "queue_depth": int(os.getenv("QUEUE_DEPTH", "0")),
                "last_successful_fetch": now.isoformat().replace("+00:00", "Z"),
            }
            await ws.send(encrypt_json(json.dumps(payload).encode()))
            print(await ws.recv())
            await asyncio.sleep(INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
