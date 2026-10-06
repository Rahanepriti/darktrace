from datetime import datetime, timedelta, timezone

import pytest

import app.health
from app.health import check_crawler_health


class FakeHeartbeatCache:
    async def get_all_heartbeats(self):
        stale_time = (
            datetime.now(timezone.utc) - timedelta(minutes=10)
        ).isoformat()

        return [
            {
                "worker_id": "cw-stale-test",
                "status": "healthy",
                "timestamp": stale_time,
                "queue_depth": 10,
                "last_successful_fetch": stale_time,
            }
        ]

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_stale_heartbeat_is_degraded(monkeypatch):
    monkeypatch.setattr(
        app.health,
        "HeartbeatCache",
        FakeHeartbeatCache,
    )

    result = await check_crawler_health()

    assert result["status"] == "degraded"
    assert result["active_workers"] == 1
    assert result["last_heartbeat"] is not None

class EmptyHeartbeatCache:
    async def get_all_heartbeats(self):
        return []

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_no_heartbeat_is_unhealthy(monkeypatch):
    monkeypatch.setattr(
        app.health,
        "HeartbeatCache",
        EmptyHeartbeatCache,
    )

    result = await check_crawler_health()

    assert result["status"] == "unhealthy"
    assert result["last_heartbeat"] is None
    assert result["active_workers"] == 0
    assert result["queue_depth"] == 0

def test_health_endpoint_shape():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    response = client.get("/api/v1/health")

    assert response.status_code == 200

    data = response.json()

    assert "status" in data
    assert "checked_at" in data
    assert "components" in data

    assert "database" in data["components"]
    assert "crawler" in data["components"]

    assert "status" in data["components"]["database"]
    assert "latency_ms" in data["components"]["database"]

    assert "status" in data["components"]["crawler"]
    assert "last_heartbeat" in data["components"]["crawler"]
    assert "active_workers" in data["components"]["crawler"]
    assert "queue_depth" in data["components"]["crawler"]
