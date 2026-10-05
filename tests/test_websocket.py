import asyncio
import json
from datetime import datetime, timezone

import pytest
import websockets

from fastapi.testclient import TestClient

from app.main import app

from app.services.crawler_health import encrypt_message

@pytest.mark.asyncio
async def test_heartbeat():
    uri = "ws://127.0.0.1:8000/api/v1/ws/health"

    async with websockets.connect(uri) as websocket:
        heartbeat = {
            "worker_id": "cw-test-01",
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "queue_depth": 14,
            "last_successful_fetch": "2026-10-01T08:59:40Z",
        }

        encrypted_heartbeat = encrypt_message(heartbeat)

        await websocket.send(encrypted_heartbeat)

        print("Encrypted heartbeat sent")


def test_encryption_roundtrip():
    message = {
        "worker_id": "cw-test-01",
        "status": "healthy",
        "queue_depth": 14,
    }

    encrypted = encrypt_message(message)

    from app.services.crawler_health import decrypt_message

    decrypted = decrypt_message(encrypted)

    assert decrypted == message
    
    
    
def test_tampered_message_rejected():
    from app.services.crawler_health import decrypt_message

    message = {
        "worker_id": "cw-test-01",
        "status": "healthy",
        "queue_depth": 14,
    }

    encrypted = encrypt_message(message)

    tampered = encrypted[:-1] + (
        "0" if encrypted[-1] != "0" else "1"
    )

    try:
        decrypt_message(tampered)
        assert False, "Tampered message was accepted"
    except Exception:
        assert True
        
        
        
        
def test_stale_heartbeat():
    from app.services.crawler_health import (
        check_crawler_health,
        store_heartbeat,
    )

    old_heartbeat = {
        "worker_id": "cw-stale-test",
        "status": "healthy",
        "timestamp": "2020-01-01T00:00:00Z",
        "queue_depth": 0,
        "last_successful_fetch": "2020-01-01T00:00:00Z",
    }

    store_heartbeat(
        "cw-stale-test",
        old_heartbeat,
        ttl=60,
    )

    result = check_crawler_health()

    assert result["status"] == "degraded"        
        


def test_health_endpoint_response_shape():
    client = TestClient(app)

    response = client.get("/api/v1/health")

    assert response.status_code == 200

    data = response.json()

    assert "status" in data
    assert "checked_at" in data
    assert "components" in data

    assert "database" in data["components"]
    assert "crawler" in data["components"]      

