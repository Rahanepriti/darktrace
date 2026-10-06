from fastapi.testclient import TestClient
from app.main import app

def test_health_response_shape():
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"healthy", "degraded", "unhealthy"}
    assert "checked_at" in data
    assert set(data["components"]) == {"database", "crawler"}
    assert "status" in data["components"]["database"]
    assert "status" in data["components"]["crawler"]
