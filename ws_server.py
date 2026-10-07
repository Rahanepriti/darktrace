"""
WebSocket endpoint the crawler connects to and sends encrypted heartbeats over.  

A bad message at any step is logged and the connection is kept open --
one malformed heartbeat must never crash the whole WS connection, let alone the server.
"""
import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from crypto_utils import decrypt, get_active_key, DecryptionError
from redis_cache import set_crawler_status
from config import REPLAY_WINDOW_SECONDS

router = APIRouter()

REQUIRED_FIELDS = {"crawler_id": str, "status": str, "ts": (int, float)}
VALID_STATUSES = {"ok", "degraded", "error"}


# Raised when decrypted JSON doesn't match the expected heartbeat schema
class ValidationError(Exception):
    pass


def validate_heartbeat(data: dict) -> None:
    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in data:
            raise ValidationError(f"missing required field '{field}'")
        if not isinstance(data[field], expected_type):
            raise ValidationError(f"field '{field}' has wrong type")

    if data["status"] not in VALID_STATUSES:
        raise ValidationError(f"unknown status '{data['status']}'")


def check_not_replayed(ts: float) -> None:
    """Rejects a heartbeat whose own claimed timestamp is older than
    REPLAY_WINDOW_SECONDS -- stops a captured message being resent
    later to fake an 'alive' crawler. Also rejects timestamps from the
    future beyond a small tolerance, which usually means clock drift
    or a deliberately forged ts."""
    now = time.time()
    age = now - ts
    if age > REPLAY_WINDOW_SECONDS:
        raise ValidationError(f"heartbeat too old ({age:.0f}s > {REPLAY_WINDOW_SECONDS}s window)")
    if age < -10:  # 10s tolerance for minor clock skew
        raise ValidationError(f"heartbeat timestamp is in the future ({-age:.0f}s ahead)")


@router.websocket("/ws/heartbeat")
async def heartbeat_endpoint(websocket: WebSocket):
    await websocket.accept()
    _, key = get_active_key()

    try:
        while True:
            raw_bytes = await websocket.receive_bytes()
            _handle_one_message(raw_bytes, key)
    except WebSocketDisconnect:
        pass  # crawler disconnected normally -- nothing to do


def _handle_one_message(raw_bytes: bytes, key: bytes) -> None:
    """Runs the full decrypt -> validate -> replay-check -> store
    pipeline for a single message. Any failure is logged and swallowed
    here so the caller's while-loop keeps running -- including the
    Redis write, which used to sit outside this try block and could
    crash the whole connection if Redis was unreachable."""
    try:
        plaintext = decrypt(raw_bytes, key)
        data = json.loads(plaintext)
        validate_heartbeat(data)
        check_not_replayed(data["ts"])
        set_crawler_status(data["crawler_id"], data["status"], data["ts"])
    except DecryptionError as exc:
        print(f"[ws] rejected message: decryption failed -- {exc}")
        return
    except (ValidationError, json.JSONDecodeError) as exc:
        print(f"[ws] rejected message: {exc}")
        return
    except Exception as exc:
        # Last-resort safety net -- e.g. Redis unreachable. A storage
        # failure must never kill the WebSocket connection; log it and
        # keep listening for the next heartbeat.
        print(f"[ws] error processing message: {exc}")
        return

    print(f"[ws] heartbeat OK: {data['crawler_id']} -> {data['status']}")