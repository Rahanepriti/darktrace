import asyncio
import json

from fastapi.testclient import TestClient

from health_service.api import app, get_cache
from health_service.cache import InMemoryHeartbeatCache
from health_service.crypto import encrypt_message
from health_service.schemas import HeartbeatPayload, utcnow


def _build_envelope(key: bytes, worker_id: str = "cw-1", status: str = "healthy") -> str:
    payload = HeartbeatPayload(
        worker_id=worker_id,
        status=status,
        timestamp=utcnow(),
        queue_depth=3,
    )
    return encrypt_message(payload.model_dump_json().encode("utf-8"), key, "v1")


def teardown_function(_fn) -> None:
    app.dependency_overrides.clear()


def test_valid_heartbeat_is_recorded_in_cache(test_key):
    cache = InMemoryHeartbeatCache()
    app.dependency_overrides[get_cache] = lambda: cache

    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/ws/health") as websocket:
            websocket.send_text(_build_envelope(test_key, worker_id="cw-1"))
            websocket.close()

    recorded = asyncio.run(cache.get_all_heartbeats())
    assert len(recorded) == 1
    assert recorded[0].worker_id == "cw-1"


def test_tampered_message_is_rejected_without_crashing_handler(test_key):
    cache = InMemoryHeartbeatCache()
    app.dependency_overrides[get_cache] = lambda: cache

    envelope = json.loads(_build_envelope(test_key, worker_id="cw-2"))
    envelope["ciphertext"] = envelope["ciphertext"][:-4] + "abcd"

    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/ws/health") as websocket:
            websocket.send_text(json.dumps(envelope))
            websocket.send_text(_build_envelope(test_key, worker_id="cw-3"))
            websocket.close()

    recorded = asyncio.run(cache.get_all_heartbeats())
    worker_ids = {entry.worker_id for entry in recorded}
    assert "cw-2" not in worker_ids
    assert "cw-3" in worker_ids


def test_malformed_json_message_does_not_crash_handler(test_key):
    cache = InMemoryHeartbeatCache()
    app.dependency_overrides[get_cache] = lambda: cache

    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/ws/health") as websocket:
            websocket.send_text("this is not an envelope at all")
            websocket.send_text(_build_envelope(test_key, worker_id="cw-4"))
            websocket.close()

    recorded = asyncio.run(cache.get_all_heartbeats())
    worker_ids = {entry.worker_id for entry in recorded}
    assert "cw-4" in worker_ids
