from __future__ import annotations


def _generate_txn_dataset(client, rows: int = 5) -> str:
    resp = client.post(
        "/generate",
        json={
            "datasets": [
                {
                    "name": "txns",
                    "rows": rows,
                    "fields": [
                        {"name": "account_id", "generator": "bothify", "type": "string",
                         "constraint": {"format": "ACC-##"}},
                        {"name": "currency", "generator": "random_element", "type": "string",
                         "constraint": {"values": "USD"}},
                        {"name": "amount", "generator": "random_int", "type": "integer",
                         "constraint": {"min": 10, "max": 100}},
                        {"name": "transaction_type", "generator": "random_element", "type": "string",
                         "constraint": {"values": "Credit,Debit"}},
                        {"name": "transaction_date", "generator": "date_between", "type": "date",
                         "constraint": {"start": "-3d", "end": "today"}},
                    ],
                }
            ],
            "homogeneity": 100,
            "seed": 11,
        },
    )
    assert resp.status_code == 200
    return resp.json()["datasets"][0]["dataset_id"]


def test_derive_balances_api_happy_path(client):
    ds_id = _generate_txn_dataset(client)

    resp = client.post(
        f"/datasets/{ds_id}/balances",
        json={"name": "balances", "account_fields": ["account_id"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["transform_type"] == "balance"
    assert body["row_count"] > 0
    assert "opening_balance" in body["columns"]
    assert "closing_balance" in body["columns"]


def test_derive_balances_api_404_for_unknown_dataset(client):
    resp = client.post(
        "/datasets/nonexistent/balances",
        json={"name": "balances", "account_fields": ["account_id"]},
    )
    assert resp.status_code == 404


def test_derive_balances_api_400_for_invalid_column(client):
    ds_id = _generate_txn_dataset(client)
    resp = client.post(
        f"/datasets/{ds_id}/balances",
        json={"name": "balances", "account_fields": ["account_id; DROP TABLE x"]},
    )
    assert resp.status_code == 400
