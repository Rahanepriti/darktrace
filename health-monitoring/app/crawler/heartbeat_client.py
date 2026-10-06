"""Crawler-side heartbeat client.

The crawler is the WebSocket CLIENT: it dials OUT to the API (egress-only zone). Each cycle it builds
a heartbeat, encrypts it with AES-256-GCM and sends it; the API replies with an encrypted ack that
carries the server's active key version (so rotation needs no redeploy).

Run standalone:   python -m app.crawler.heartbeat_client
Embed in a crawler: HeartbeatClient(url, token, crypto, worker_id, my_status_provider).run(stop_event)
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import random
import signal
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Union

from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger, log_event
from app.core.security import build_key_provider
from app.crypto.aes_gcm import CryptoError, CryptoService
from app.schemas.health import WorkerStatus

log = get_logger("heartbeat_client")


@dataclass
class WorkerSnapshot:
    status: WorkerStatus
    queue_depth: int
    last_successful_fetch: datetime | None = None


StatusProvider = Callable[[], Union[WorkerSnapshot, Awaitable[WorkerSnapshot]]]


class DemoStatusProvider:
    """Synthetic data so the module can be exercised without a real crawler."""

    def __call__(self) -> WorkerSnapshot:
        return WorkerSnapshot(WorkerStatus.healthy, random.randint(0, 50), datetime.now(timezone.utc))


class HeartbeatClient:
    def __init__(
        self,
        url: str,
        token: str,
        crypto: CryptoService,
        worker_id: str,
        status_provider: StatusProvider,
        interval_seconds: float = 20,
        ack_timeout_seconds: float = 5,
        allow_insecure: bool = False,
    ):
        if url.startswith("ws://") and not allow_insecure:
            raise ValueError("refusing plain ws:// URL; use wss:// (set allow_insecure only for local development)")
        self._url, self._token, self._crypto = url, token, crypto
        self._worker_id, self._provider = worker_id, status_provider
        self._interval, self._ack_timeout = interval_seconds, ack_timeout_seconds
        self._hinted_version: int | None = None

    async def build_message(self) -> str:
        snap = self._provider()
        if inspect.isawaitable(snap):
            snap = await snap
        payload = {
            "worker_id": self._worker_id,
            "status": snap.status.value,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "queue_depth": snap.queue_depth,
            "last_successful_fetch": snap.last_successful_fetch.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            if snap.last_successful_fetch else None,
        }
        version = self._hinted_version if self._hinted_version in self._crypto.versions else None
        return self._crypto.encrypt(json.dumps(payload).encode(), version)

    def handle_reply(self, token: str) -> dict[str, Any]:
        try:
            doc = json.loads(self._crypto.decrypt(token).plaintext)
        except (CryptoError, ValueError):
            raise ConnectionError("undecryptable reply from server") from None
        hinted = doc.get("active_key_version")
        if doc.get("ok") and isinstance(hinted, int) and hinted != self._hinted_version and hinted in self._crypto.versions:
            self._hinted_version = hinted
            log_event(log, logging.INFO, "switched to server-advertised key version", key_version=hinted)
        return doc

    async def _sleep(self, stop: asyncio.Event, seconds: float) -> None:
        try:
            await asyncio.wait_for(stop.wait(), seconds)
        except asyncio.TimeoutError:
            pass

    async def run(self, stop: asyncio.Event | None = None) -> None:
        stop = stop or asyncio.Event()
        failures = 0
        while not stop.is_set():
            try:
                async with connect(
                    self._url,
                    additional_headers={"Authorization": f"Bearer {self._token}"},
                    open_timeout=10,
                    max_size=64 * 1024,
                ) as ws:
                    log_event(log, logging.INFO, "connected to health API", worker_id=self._worker_id)
                    while not stop.is_set():
                        await ws.send(await self.build_message())
                        reply = self.handle_reply(await asyncio.wait_for(ws.recv(), self._ack_timeout))
                        if reply.get("ok"):
                            failures = 0
                            log_event(log, logging.INFO, "heartbeat sent", worker_id=self._worker_id)
                        else:
                            log_event(log, logging.WARNING, "heartbeat rejected by server", reason=reply.get("reason"))
                        await self._sleep(stop, self._interval * random.uniform(0.9, 1.1))
            except (OSError, WebSocketException, asyncio.TimeoutError, ConnectionError) as exc:
                failures += 1
                delay = min(60.0, 2.0 ** min(failures, 6)) * random.uniform(0.5, 1.0)
                log_event(log, logging.WARNING, "connection lost; will retry", exc_type=type(exc).__name__,
                          retry_in_seconds=round(delay, 1))
                await self._sleep(stop, delay)


async def _main() -> None:
    s: Settings = get_settings()
    configure_logging(s.log_level)
    client = HeartbeatClient(
        url=s.health_ws_url,
        token=s.crawler_ws_token,
        crypto=CryptoService(build_key_provider(s), s.key_refresh_seconds),
        worker_id=s.worker_id,
        status_provider=DemoStatusProvider(),
        interval_seconds=s.heartbeat_interval_seconds,
        allow_insecure=s.app_env != "production",
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            pass
    await client.run(stop)


if __name__ == "__main__":
    asyncio.run(_main())
