from fastapi.testclient import TestClient

from health_service import config
from health_service.api import app, crawler_dependency, database_dependency
from health_service.schemas import CrawlerComponent, DatabaseComponent


def _override(database: DatabaseComponent, crawler: CrawlerComponent):
    app.dependency_overrides[database_dependency] = lambda: database
    app.dependency_overrides[crawler_dependency] = lambda: crawler


def teardown_function(_fn) -> None:
    app.dependency_overrides.clear()


def test_healthy_response_has_full_section_4_shape():
    _override(
        DatabaseComponent(status="healthy", latency_ms=12),
        CrawlerComponent(status="healthy", active_workers=8, queue_depth=14),
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert "checked_at" in body
    assert body["components"]["database"] == {"status": "healthy", "latency_ms": 12}
    assert body["components"]["crawler"]["status"] == "healthy"
    assert body["components"]["crawler"]["active_workers"] == 8
    assert body["components"]["crawler"]["queue_depth"] == 14


def test_database_unreachable_returns_unhealthy():
    _override(
        DatabaseComponent(status="unhealthy", latency_ms=None),
        CrawlerComponent(status="healthy", active_workers=8, queue_depth=14),
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "unhealthy"


def test_stale_crawler_heartbeat_returns_degraded():
    _override(
        DatabaseComponent(status="healthy", latency_ms=10),
        CrawlerComponent(status="degraded", active_workers=5, queue_depth=14),
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


def test_no_heartbeats_at_all_returns_unhealthy():
    _override(
        DatabaseComponent(status="healthy", latency_ms=10),
        CrawlerComponent(status="unhealthy", active_workers=0, queue_depth=0),
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "unhealthy"


def test_minimal_response_when_detailed_requires_auth(monkeypatch):
    monkeypatch.setattr(config, "HEALTH_DETAILED_REQUIRES_AUTH", True)
    monkeypatch.setattr(config, "HEALTH_API_KEY", "secret-key")
    _override(
        DatabaseComponent(status="healthy", latency_ms=10),
        CrawlerComponent(status="healthy", active_workers=5, queue_depth=14),
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"status", "checked_at"}


def test_full_response_when_valid_api_key_supplied(monkeypatch):
    monkeypatch.setattr(config, "HEALTH_DETAILED_REQUIRES_AUTH", True)
    monkeypatch.setattr(config, "HEALTH_API_KEY", "secret-key")
    _override(
        DatabaseComponent(status="healthy", latency_ms=10),
        CrawlerComponent(status="healthy", active_workers=5, queue_depth=14),
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/health", headers={"x-api-key": "secret-key"})

    assert response.status_code == 200
    body = response.json()
    assert "components" in body
