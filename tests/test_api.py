from fastapi.testclient import TestClient

from vicap.api.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "kimi_model" in data


def test_list_clips():
    r = client.get("/api/v1/clips")
    assert r.status_code == 200
    assert "clips" in r.json()


def test_health_no_auth():
    """Health endpoint should not require API key."""
    r = client.get("/api/v1/health")
    assert r.status_code == 200
