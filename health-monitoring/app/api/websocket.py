"""WebSocket endpoints.

/api/v1/ws/health  - crawler -> API (crawler is the CLIENT; the API never connects out).
/api/v1/ws/monitor - operator dashboards <- API (live snapshots; first message must authenticate).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.container import Container, get_container
from app.core.logging import get_logger, log_event
from app.core.security import verify_bearer
from app.crypto.aes_gcm import CryptoError

router = APIRouter(prefix="/api/v1", tags=["websocket"])
log = get_logger("websocket")


def _peer(ws: WebSocket) -> str:
    return ws.client.host if ws.client else "unknown"


async def _reply(ws: WebSocket, c: Container, doc: dict) -> None:
    try:
        await ws.send_text(c.crypto.encrypt(json.dumps(doc).encode()))
    except CryptoError:
        log_event(log, logging.ERROR, "cannot encrypt reply")


@router.websocket("/ws/health")
async def crawler_heartbeat(ws: WebSocket) -> None:
    c = get_container(ws)
    peer = _peer(ws)
    # Auth BEFORE accept, via header (never URL/query string).
    if not verify_bearer(ws.headers.get("authorization"), c.settings.crawler_ws_token):
        log_event(log, logging.WARNING, "crawler connection refused", peer=peer, reason="unauthorized")
        await ws.close(code=1008)
        return

    await ws.accept()
    log_event(log, logging.INFO, "crawler connected", peer=peer)
    rejects = 0
    try:
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive(), c.settings.ws_idle_timeout_seconds)
            except asyncio.TimeoutError:
                log_event(log, logging.WARNING, "crawler idle timeout", peer=peer)
                await ws.close(code=1001)
                return
            if msg["type"] == "websocket.disconnect":
                return

            raw = msg.get("text")
            if raw is None:
                result_ok, reason = False, "invalid_frame"
                log_event(log, logging.WARNING, "heartbeat rejected", reason=reason, peer=peer)
            elif len(raw.encode()) > c.settings.ws_max_message_bytes:
                result_ok, reason = False, "payload_too_large"
                log_event(log, logging.WARNING, "heartbeat rejected", reason=reason, peer=peer)
            else:
                res = await c.processor.process(raw, peer=peer)
                result_ok, reason = res.ok, res.reason

            if result_ok:
                rejects = 0
                await _reply(ws, c, {
                    "type": "ack", "ok": True,
                    "active_key_version": c.crypto.active_version,
                    "server_time": datetime.now(timezone.utc).isoformat(),
                })
            else:
                rejects += 1
                await _reply(ws, c, {"type": "nack", "ok": False, "reason": reason})
                if rejects >= c.settings.ws_max_consecutive_rejects:
                    log_event(log, logging.WARNING, "closing connection: too many rejects", peer=peer)
                    await ws.close(code=1008)
                    return
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # never let one connection take the API down
        log_event(log, logging.ERROR, "websocket handler error", peer=peer, exc_type=type(exc).__name__)
        try:
            await ws.close(code=1011)
        except Exception:
            pass
    finally:
        log_event(log, logging.INFO, "crawler disconnected", peer=peer)


@router.websocket("/ws/monitor")
async def monitor(ws: WebSocket) -> None:
    c = get_container(ws)
    peer = _peer(ws)
    if not c.settings.monitor_enabled or c.monitor_connections >= c.settings.monitor_max_connections:
        await ws.close(code=1013)
        return
    await ws.accept()
    c.monitor_connections += 1
    try:
        # Browsers cannot set WS headers, so the token travels in the first message (never the URL).
        try:
            first = json.loads(await asyncio.wait_for(ws.receive_text(), 5))
            token = first.get("token", "") if isinstance(first, dict) and first.get("type") == "auth" else ""
        except (asyncio.TimeoutError, ValueError, AttributeError):
            token = ""
        if not verify_bearer(f"Bearer {token}", c.settings.health_api_token):
            log_event(log, logging.WARNING, "monitor connection refused", peer=peer)
            await ws.close(code=1008)
            return
        log_event(log, logging.INFO, "monitor connected", peer=peer)
        while True:
            report = await c.health_service.check_cached(max_age_seconds=1.0)
            await ws.send_json({"type": "snapshot", "data": report.model_dump(mode="json", exclude_none=True)})
            try:  # wait for the next tick, but notice disconnects immediately
                msg = await asyncio.wait_for(ws.receive(), c.settings.monitor_push_interval_seconds)
                if msg["type"] == "websocket.disconnect":
                    return
            except asyncio.TimeoutError:
                continue
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log_event(log, logging.ERROR, "monitor handler error", peer=peer, exc_type=type(exc).__name__)
    finally:
        c.monitor_connections -= 1
