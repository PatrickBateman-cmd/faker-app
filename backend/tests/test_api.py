from __future__ import annotations

import pytest


def test_list_templates(client):
    resp = client.get("/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_generate_and_crud(client):
    body = {
        "datasets": [
            {
                "name": "api_test",
                "rows": 5,
                "fields": [
                    {"name": "name", "generator": "name", "type": "string"},
                    {"name": "email", "generator": "email", "type": "string"},
                ],
            }
        ],
        "homogeneity": 100,
        "seed": 42,
    }

    # Generate
    resp = client.post("/generate", json=body)
    assert resp.status_code == 200
    gen = resp.json()
    assert len(gen["datasets"]) == 1
    ds_id = gen["datasets"][0]["dataset_id"]

    # Get dataset
    resp = client.get(f"/datasets/{ds_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "api_test"

    # Get rows
    resp = client.get(f"/datasets/{ds_id}/rows")
    assert resp.status_code == 200
    assert resp.json()["total"] == 5
    assert len(resp.json()["rows"]) == 5

    # Get columns
    resp = client.get(f"/datasets/{ds_id}/columns")
    assert resp.status_code == 200
    col_names = [c["name"] for c in resp.json()]
    assert "name" in col_names
    assert "email" in col_names

    # List datasets
    resp = client.get("/datasets")
    assert resp.status_code == 200
    assert ds_id in [d["dataset_id"] for d in resp.json()]

    # Delete
    resp = client.delete(f"/datasets/{ds_id}")
    assert resp.status_code == 204

    # Verify deleted
    resp = client.get(f"/datasets/{ds_id}")
    assert resp.status_code == 404

    resp = client.get(f"/datasets/{ds_id}/rows")
    assert resp.status_code == 404


def test_generate_pagination(client):
    body = {
        "datasets": [
            {
                "name": "page_test",
                "rows": 20,
                "fields": [{"name": "name", "generator": "name", "type": "string"}],
            }
        ],
        "homogeneity": 100,
        "seed": 1,
    }
    resp = client.post("/generate", json=body)
    ds_id = resp.json()["datasets"][0]["dataset_id"]

    # First page of 10
    resp = client.get(f"/datasets/{ds_id}/rows?page=1&per_page=10")
    assert resp.status_code == 200
    assert resp.json()["total"] == 20
    assert len(resp.json()["rows"]) == 10

    # Second page
    resp = client.get(f"/datasets/{ds_id}/rows?page=2&per_page=10")
    assert resp.status_code == 200
    assert len(resp.json()["rows"]) == 10


def test_aggregate_via_api(client):
    body = {
        "datasets": [
            {
                "name": "agg_api",
                "rows": 10,
                "fields": [
                    {"name": "grp", "generator": "random_element", "type": "string",
                     "constraint": {"values": "X,Y"}},
                    {"name": "val", "generator": "random_int", "type": "integer"},
                ],
            }
        ],
        "homogeneity": 100,
        "seed": 42,
    }
    resp = client.post("/generate", json=body)
    ds_id = resp.json()["datasets"][0]["dataset_id"]

    agg_req = {
        "name": "agg_api_result",
        "group_by": ["grp"],
        "aggregations": [{"column": "val", "function": "sum", "alias": "total"}],
    }
    resp = client.post(f"/datasets/{ds_id}/aggregate", json=agg_req)
    assert resp.status_code == 200
    data = resp.json()
    assert data["transform_type"] == "aggregate"
    assert data["row_count"] == 2


def test_dedup_via_api(client):
    body = {
        "datasets": [
            {
                "name": "dedup_api",
                "rows": 10,
                "fields": [
                    {"name": "email", "generator": "random_element", "type": "string",
                     "constraint": {"values": "a@x.com,b@x.com"}},
                    {"name": "score", "generator": "random_int", "type": "integer"},
                ],
            }
        ],
        "homogeneity": 100,
        "seed": 42,
    }
    resp = client.post("/generate", json=body)
    ds_id = resp.json()["datasets"][0]["dataset_id"]

    dedup_req = {
        "name": "dedup_api_result",
        "keys": ["email"],
        "strategy": "keep_first",
    }
    resp = client.post(f"/datasets/{ds_id}/dedup", json=dedup_req)
    assert resp.status_code == 200
    data = resp.json()
    assert data["transform_type"] == "dedup"
    assert data["row_count"] == 2


def test_get_nonexistent_dataset(client):
    resp = client.get("/datasets/nonexistent-id")
    assert resp.status_code == 404


def test_delete_nonexistent_dataset(client):
    resp = client.delete("/datasets/nonexistent-id")
    assert resp.status_code == 404
