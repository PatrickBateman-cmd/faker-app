from __future__ import annotations


def test_get_breaks_empty_for_unknown_run(client):
    resp = client.get("/generate/runs/999999/breaks")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_breaks_returns_persisted_records(client):
    gen_resp = client.post(
        "/generate",
        json={
            "datasets": [
                {"name": "gl", "rows": 5, "fields": [
                    {"name": "trade_id", "generator": "uuid4", "type": "string"},
                    {"name": "amount", "generator": "random_int", "type": "integer",
                     "constraint": {"min": 1000, "max": 9999}},
                ]},
                {"name": "subledger", "rows": 5, "fields": [
                    {"name": "trade_id", "generator": "uuid4", "type": "string"},
                    {"name": "amount", "generator": "random_int", "type": "integer",
                     "constraint": {"min": 1000, "max": 9999}},
                ]},
            ],
            "homogeneity": 100,
            "seed": 7,
            "reconciliation_mode": True,
            "exact_fields": ["trade_id", "amount"],
            "field_breaks": [{"field_name": "amount", "break_rate": 1.0, "break_style": "drift", "drift_pct": 0.1}],
        },
    )
    assert gen_resp.status_code == 200
    run_id = gen_resp.json()["run_id"]
    break_count = gen_resp.json()["break_count"]
    assert break_count == 5

    breaks_resp = client.get(f"/generate/runs/{run_id}/breaks")
    assert breaks_resp.status_code == 200
    records = breaks_resp.json()
    assert len(records) == 5
    assert all(r["field_name"] == "amount" for r in records)
    assert all(r["run_id"] == run_id for r in records)
