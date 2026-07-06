from fastapi.testclient import TestClient

from vicap.api.main import app

client = TestClient(app)


def test_health():
    """Health should return 200 with status ok."""
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "kimi_model" in data
    assert "db_connected" in data


def test_health_no_auth():
    """Health endpoint should not require API key."""
    r = client.get("/api/v1/health")
    assert r.status_code == 200


def test_metrics():
    """Prometheus /metrics endpoint should be accessible."""
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "vicap_http_requests_total" in r.text


def test_list_clips():
    """GET /api/v1/clips should return list."""
    r = client.get("/api/v1/clips")
    assert r.status_code == 200
    data = r.json()
    assert "clips" in data


def test_sessions_requires_auth():
    """Sessions endpoints should require API key."""
    r = client.get("/api/v1/sessions")
    assert r.status_code == 401  # Missing X-API-Key


def test_session_get_404():
    """Non-existent session should return 404."""
    headers = {"X-API-Key": "test-key-123"}
    r = client.get("/api/v1/sessions/nonexistent-id", headers=headers)
    assert r.status_code == 404


def test_jobs_requires_auth():
    """Jobs endpoints should require API key."""
    r = client.get("/api/v1/jobs")
    assert r.status_code == 401


def test_job_get_404():
    """Non-existent job should return 404."""
    headers = {"X-API-Key": "test-key-123"}
    r = client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000", headers=headers)
    assert r.status_code == 404


def test_admin_usage_requires_auth():
    """Admin endpoints should require API key."""
    r = client.get("/api/v1/admin/usage")
    assert r.status_code == 401


def test_root_redirect():
    """Root should serve demo or return something."""
    r = client.get("/")
    assert r.status_code in (200, 404)
