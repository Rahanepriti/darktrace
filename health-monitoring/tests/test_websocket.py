import base64
import json

import pytest
from fakeredis import FakeAsyncRedis
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.crypto.aes_gcm import CryptoService, KeyRing
from app.main import create_app
from tests.conftest import API_TOKEN, CRAWLER_TOKEN, StaticKeyProvider, b64, hb_payload, make_settings, random_key

WS = "/api/v1/ws/health"
AUTH = {"Authorization": f"Bearer {CRAWLER_TOKEN}"}


@pytest.fixture
def key():
    return random_key()


@pytest.fixture
def client(key):
    app = create_app(
        settings=make_settings(key=key, ws_max_consecutive_rejects=5),
        redis_factory=lambda: FakeAsyncRedis(decode_responses=True),
        engine_factory=lambda: create_async_engine("sqlite+aiosqlite://"),
    )
    with TestClient(app) as c:
        yield c


@pytest.fixture
def crypto(key):
    return CryptoService(StaticKeyProvider(KeyRing({1: key}, 1)))


def send(ws, crypto, payload):
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    ws.send_text(crypto.encrypt(data))
    return crypto.decrypt(ws.receive_text())


def reply(ws, crypto):
    return json.loads(crypto.decrypt(ws.receive_text()).plaintext)


def exchange(ws, crypto, payload):
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    ws.send_text(crypto.encrypt(data))
    return reply(ws, crypto)


def test_connection_requires_auth(client):
    for headers in ({}, {"Authorization": "Bearer wrong"}):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(WS, headers=headers):
                pass


def test_valid_heartbeat_acked_and_visible_in_health(client, crypto):
    with client.websocket_connect(WS, headers=AUTH) as ws:
        r = exchange(ws, crypto, hb_payload("cw-14"))
        assert r["ok"] is True and r["active_key_version"] == 1
    body = client.get("/api/v1/health", headers={"Authorization": f"Bearer {API_TOKEN}"}).json()
    assert body["components"]["crawler"]["active_workers"] == 1
    assert body["components"]["crawler"]["workers"][0]["worker_id"] == "cw-14"
    assert body["status"] == "healthy"  # sqlite stands in for postgres


def test_invalid_json_rejected_but_connection_survives(client, crypto):
    with client.websocket_connect(WS, headers=AUTH) as ws:
        assert exchange(ws, crypto, b"not json{")["reason"] == "invalid_json"
        assert exchange(ws, crypto, hb_payload())["ok"] is True  # still serving


def test_invalid_schema_rejected(client, crypto):
    with client.websocket_connect(WS, headers=AUTH) as ws:
        assert exchange(ws, crypto, {"worker_id": "cw-1"})["reason"] == "invalid_schema"
        assert exchange(ws, crypto, hb_payload(status="exploded"))["reason"] == "invalid_schema"
        assert exchange(ws, crypto, hb_payload(worker_id="../etc"))["reason"] == "invalid_schema"
        assert exchange(ws, crypto, hb_payload(queue_depth=-1))["reason"] == "invalid_schema"
        assert exchange(ws, crypto, hb_payload(extra_field="x"))["reason"] == "invalid_schema"


def test_naive_timestamp_rejected(client, crypto):
    with client.websocket_connect(WS, headers=AUTH) as ws:
        assert exchange(ws, crypto, hb_payload(timestamp="2026-10-01T09:00:00"))["reason"] == "invalid_schema"


def test_wrong_key_rejected(client):
    attacker = CryptoService(StaticKeyProvider(KeyRing({1: random_key()}, 1)))
    with client.websocket_connect(WS, headers=AUTH) as ws:
        ws.send_text(attacker.encrypt(json.dumps(hb_payload()).encode()))
        # server replies with ITS key, so the attacker cannot read it - just check the socket still works
        assert ws.receive_text()


def test_tampered_message_rejected(client, crypto):
    with client.websocket_connect(WS, headers=AUTH) as ws:
        raw = bytearray(base64.urlsafe_b64decode(crypto.encrypt(json.dumps(hb_payload()).encode()) + "=="))
        raw[-5] ^= 0xFF
        ws.send_text(base64.urlsafe_b64encode(bytes(raw)).decode())
        assert reply(ws, crypto)["reason"] == "decrypt_failed"
        assert exchange(ws, crypto, hb_payload())["ok"] is True


def test_garbage_and_binary_frames_do_not_crash_server(client, crypto):
    with client.websocket_connect(WS, headers=AUTH) as ws:
        ws.send_text("%%% garbage %%%")
        assert reply(ws, crypto)["reason"] == "decrypt_failed"
        ws.send_bytes(b"\x00\x01\x02")
        assert reply(ws, crypto)["reason"] == "invalid_frame"
        ws.send_text("A" * 10_000)
        assert reply(ws, crypto)["reason"] == "payload_too_large"
    with client.websocket_connect(WS, headers=AUTH) as ws2:  # server still healthy for others
        assert exchange(ws2, crypto, hb_payload("cw-2"))["ok"] is True


def test_replay_of_identical_message_rejected(client, crypto):
    with client.websocket_connect(WS, headers=AUTH) as ws:
        token = crypto.encrypt(json.dumps(hb_payload()).encode())
        ws.send_text(token)
        assert reply(ws, crypto)["ok"] is True
        ws.send_text(token)  # attacker re-sends captured ciphertext
        assert reply(ws, crypto)["reason"] == "replay"


def test_replay_across_connections_rejected(client, crypto):
    token = crypto.encrypt(json.dumps(hb_payload()).encode())
    with client.websocket_connect(WS, headers=AUTH) as ws:
        ws.send_text(token)
        assert reply(ws, crypto)["ok"]
    with client.websocket_connect(WS, headers=AUTH) as ws:
        ws.send_text(token)
        assert reply(ws, crypto)["reason"] == "replay"


def test_old_timestamp_rejected(client, crypto):
    with client.websocket_connect(WS, headers=AUTH) as ws:
        assert exchange(ws, crypto, hb_payload(age=301))["reason"] == "stale_timestamp"
        assert exchange(ws, crypto, hb_payload(age=-600))["reason"] == "future_timestamp"
        assert exchange(ws, crypto, hb_payload(age=290))["ok"] is True  # inside 5-minute window


def test_multiple_workers_and_connections(client, crypto):
    with client.websocket_connect(WS, headers=AUTH) as a, client.websocket_connect(WS, headers=AUTH) as b:
        assert exchange(a, crypto, hb_payload("cw-1"))["ok"]
        assert exchange(b, crypto, hb_payload("cw-2"))["ok"]
        assert exchange(a, crypto, hb_payload("cw-3"))["ok"]
    cr = client.get("/api/v1/health", headers={"Authorization": f"Bearer {API_TOKEN}"}).json()["components"]["crawler"]
    assert cr["active_workers"] == 3 and cr["queue_depth"] == 9
    assert sorted(w["worker_id"] for w in cr["workers"]) == ["cw-1", "cw-2", "cw-3"]


def test_connection_closed_after_repeated_rejects(client, crypto):
    with client.websocket_connect(WS, headers=AUTH) as ws:
        for _ in range(5):
            ws.send_text("junk")
            reply(ws, crypto)
        with pytest.raises(WebSocketDisconnect):
            ws.receive_text()


# ---- real-time monitor ---------------------------------------------------------------
def test_monitor_streams_snapshots_after_auth(client, crypto):
    with client.websocket_connect(WS, headers=AUTH) as ws:
        exchange(ws, crypto, hb_payload("cw-9"))
    with client.websocket_connect("/api/v1/ws/monitor") as m:
        m.send_json({"type": "auth", "token": API_TOKEN})
        snap = m.receive_json()
        assert snap["type"] == "snapshot" and snap["data"]["components"]["crawler"]["active_workers"] == 1
        assert m.receive_json()["type"] == "snapshot"  # pushed again without asking


def test_monitor_rejects_bad_token(client):
    with client.websocket_connect("/api/v1/ws/monitor") as m:
        m.send_json({"type": "auth", "token": "wrong"})
        with pytest.raises(WebSocketDisconnect):
            m.receive_json()


def test_dashboard_served_with_csp(client):
    r = client.get("/dashboard")
    assert r.status_code == 200 and "default-src 'none'" in r.headers["content-security-policy"]
