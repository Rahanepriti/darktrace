""" Crawler-side WebSocket client. --- This is NOT the production crawler code --
A simulator to test ws_server.py end-to-end without needing the real crawler team's code. 

it connects OUTBOUND to the API, never accepts incoming connections, encrypts every message before sending.

Run directly: python crawler_client.py
"""
import asyncio
import json
import time

import websockets

import config  # noqa: F401 -- imported for its side effect: load_dotenv()
from crypto_utils import encrypt, get_active_key

WS_URL = "ws://localhost:8001/ws/heartbeat"
CRAWLER_ID = "crawler-01"
SEND_INTERVAL_SECONDS = 5


async def send_heartbeats_forever():
    _, key = get_active_key()

    async with websockets.connect(WS_URL) as ws:
        print(f"[crawler] connected to {WS_URL}")
        while True:
            heartbeat = {
                "crawler_id": CRAWLER_ID,
                "status": "ok",
                "ts": time.time(),
            }
            plaintext = json.dumps(heartbeat).encode("utf-8")
            encrypted = encrypt(plaintext, key)

            await ws.send(encrypted)
            print(f"[crawler] sent heartbeat: {heartbeat}")

            await asyncio.sleep(SEND_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(send_heartbeats_forever())