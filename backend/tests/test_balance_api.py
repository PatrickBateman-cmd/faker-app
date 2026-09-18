from __future__ import annotations


def _balance_payload(rows: int = 40):
    return {
        "datasets": [
            {
                "name": "txns",
                "rows": rows,
                "fields": [
                    {"name": "txn_id", "generator": "uuid4", "type": "string", "unique": True},
                    {
                        "name": "account",
                        "generator": "random_element",
                        "type": "string",
                        "constraint": {"values": "ACC-1,ACC-2"},
                    },
                    {
                        "name": "amount",
                        "generator": "pydecimal",
                        "type": "float",
                        "constraint": {"min": -500, "max": 500, "right_digits": 2},
                    },
                    {
                        "name": "posting_date",
                        "generator": "date_between",
                        "type": "date",
                        "constraint": {"start": "-5d", "end": "today"},
                    },
                ],
            }
        ],
        "homogeneity": 100,
        "seed": 7,
        "reconciliation_mode": True,
        "balances": [
            {
                "name": "balances",
                "source_dataset": "txns",
                "date_field": "posting_date",
                "amount_field": "amount",
                "group_by": ["account"],
                "opening_balance": 0.0,
                "days": 5,
                "records_per_day": 8,
            }
        ],
    }


def test_generate_with_balances_returns_balance_dataset(client):
    resp = client.post("/generate", json=_balance_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["datasets"]) == 2
    balance_ds = body["datasets"][1]
    assert balance_ds["name"] == "balances"
    assert balance_ds["columns"] == [
        "partition_date",
        "account",
        "opening_balance",
        "sum_positives",
        "sum_negatives",
        "closing_balance",
        "record_count",
    ]
    assert balance_ds["row_count"] > 0


def test_balances_endpoint_returns_persisted_sets(client):
    gen_resp = client.post("/generate", json=_balance_payload())
    assert gen_resp.status_code == 200
    run_id = gen_resp.json()["run_id"]

    bal_resp = client.get(f"/generate/runs/{run_id}/balances")
    assert bal_resp.status_code == 200
    records = bal_resp.json()
    assert len(records) == 1
    rec = records[0]
    assert rec["run_id"] == run_id
    assert rec["source_dataset"] == "txns"
    assert rec["name"] == "balances"
    assert "date_field" in rec["config_json"]


def test_balances_endpoint_empty_for_unknown_run(client):
    resp = client.get("/generate/runs/999999/balances")
    assert resp.status_code == 200
    assert resp.json() == []


def test_balance_scaling_violation_rejected(client):
    payload = _balance_payload()
    payload["balances"][0]["records_per_day"] = 8  # rows=40 but 5*8=40 is valid...
    payload["datasets"][0]["rows"] = 30  # ...now mismatch
    resp = client.post("/generate", json=payload)
    assert resp.status_code == 400
    assert "days × records_per_day" in resp.json()["detail"]