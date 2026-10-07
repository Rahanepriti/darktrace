#Fake crawler - simulator for test  

import asyncio
import json
import time

import websockets

#import config   
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