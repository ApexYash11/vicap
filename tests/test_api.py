from fastapi.testclient import TestClient

from vicap.api.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "kimi_model" in data


def test_list_clips():
    r = client.get("/clips")
    assert r.status_code == 200
    assert "clips" in r.json()
