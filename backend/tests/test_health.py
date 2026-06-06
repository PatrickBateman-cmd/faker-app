def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["duckdb"] == "connected"


def test_info_returns_stats(client):
    resp = client.get("/info")
    assert resp.status_code == 200
    data = resp.json()
    assert "datasets" in data
    assert "templates" in data
    assert "runs" in data
    assert "total_rows" in data
    assert isinstance(data["recent_datasets"], list)
