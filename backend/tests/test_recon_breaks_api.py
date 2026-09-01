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


def _generate_recon_run(client, rows: int = 5) -> dict:
    resp = client.post(
        "/generate",
        json={
            "datasets": [
                {"name": "gl", "rows": rows, "fields": [
                    {"name": "trade_id", "generator": "uuid4", "type": "string"},
                    {"name": "amount", "generator": "random_int", "type": "integer",
                     "constraint": {"min": 1000, "max": 9999}},
                ]},
                {"name": "subledger", "rows": rows, "fields": [
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
    assert resp.status_code == 200
    return resp.json()


def test_get_breaks_pagination_limit(client):
    gen = _generate_recon_run(client, rows=5)
    run_id = gen["run_id"]
    assert gen["break_count"] == 5

    resp = client.get(f"/generate/runs/{run_id}/breaks", params={"limit": 2})
    assert resp.status_code == 200
    records = resp.json()
    assert len(records) == 2


def test_get_breaks_pagination_offset(client):
    gen = _generate_recon_run(client, rows=5)
    run_id = gen["run_id"]

    all_records = client.get(f"/generate/runs/{run_id}/breaks", params={"limit": 100}).json()
    assert len(all_records) == 5

    page1 = client.get(f"/generate/runs/{run_id}/breaks", params={"limit": 2, "offset": 0}).json()
    page2 = client.get(f"/generate/runs/{run_id}/breaks", params={"limit": 2, "offset": 2}).json()
    assert [r["id"] for r in page1] == [r["id"] for r in all_records[:2]]
    assert [r["id"] for r in page2] == [r["id"] for r in all_records[2:4]]


def test_delete_dataset_cascades_recon_breaks(client):
    gen = _generate_recon_run(client, rows=5)
    run_id = gen["run_id"]
    assert gen["break_count"] == 5

    # field_breaks apply to every non-first dataset in reconciliation_mode.
    target_dataset_id = gen["datasets"][1]["dataset_id"]

    del_resp = client.delete(f"/datasets/{target_dataset_id}")
    assert del_resp.status_code == 204

    breaks_resp = client.get(f"/generate/runs/{run_id}/breaks")
    assert breaks_resp.status_code == 200
    records = breaks_resp.json()
    assert records == []
