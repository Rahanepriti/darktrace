"""Real sockets: uvicorn server + the real crawler HeartbeatClient (outbound WebSocket)."""
import asyncio
import socket

import httpx
import uvicorn
from fakeredis import FakeAsyncRedis
from sqlalchemy.ext.asyncio import create_async_engine

from app.crawler.heartbeat_client import DemoStatusProvider, HeartbeatClient
from app.crypto.aes_gcm import CryptoService, KeyRing
from app.main import create_app
from tests.conftest import API_TOKEN, CRAWLER_TOKEN, StaticKeyProvider, make_settings, random_key


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_crawler_client_to_server_end_to_end():
    key = random_key()
    app = create_app(settings=make_settings(key=key),
                     redis_factory=lambda: FakeAsyncRedis(decode_responses=True),
                     engine_factory=lambda: create_async_engine("sqlite+aiosqlite://"))
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    server_task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)

    crypto = CryptoService(StaticKeyProvider(KeyRing({1: key}, 1)))
    client = HeartbeatClient(f"ws://127.0.0.1:{port}/api/v1/ws/health", CRAWLER_TOKEN, crypto, "cw-e2e",
                             DemoStatusProvider(), interval_seconds=0.5, allow_insecure=True)
    stop = asyncio.Event()
    crawler_task = asyncio.create_task(client.run(stop))
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as http:
            body = {}
            for _ in range(40):
                body = (await http.get("/api/v1/health", headers={"Authorization": f"Bearer {API_TOKEN}"})).json()
                if body["components"]["crawler"]["active_workers"] == 1:
                    break
                await asyncio.sleep(0.25)
        assert body["status"] == "healthy"
        assert body["components"]["crawler"]["workers"][0]["worker_id"] == "cw-e2e"
    finally:
        stop.set()
        await asyncio.wait_for(crawler_task, 5)
        server.should_exit = True
        await asyncio.wait_for(server_task, 10)


def test_client_refuses_plaintext_ws_by_default():
    import pytest
    crypto = CryptoService(StaticKeyProvider(KeyRing({1: random_key()}, 1)))
    with pytest.raises(ValueError):
        HeartbeatClient("ws://example.com/x", "t", crypto, "cw-1", DemoStatusProvider())
