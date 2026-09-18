from __future__ import annotations

import pytest

from app.core.database import DuckDBManager
from app.schemas.generation import (
    BalanceConfig,
    ConstraintConfig,
    DatasetDefinition,
    FieldDefinition,
    GenerateRequest,
)
from app.services.generation_engine import generate_datasets
from app.services.generation_engine.balance import _continuity_rows, build_balance_sql

_BALANCE_COLUMNS = [
    "partition_date",
    "account",
    "opening_balance",
    "sum_positives",
    "sum_negatives",
    "closing_balance",
    "record_count",
]


def _txn_request(rows: int = 50, seed: int = 42, balance: BalanceConfig | None = None):
    return GenerateRequest(
        datasets=[
            DatasetDefinition(
                name="txns",
                rows=rows,
                fields=[
                    FieldDefinition(name="txn_id", generator="uuid4", type="string", unique=True),
                    FieldDefinition(
                        name="account",
                        generator="random_element",
                        type="string",
                        constraint=ConstraintConfig(values="ACC-1,ACC-2,ACC-3"),
                    ),
                    FieldDefinition(
                        name="amount",
                        generator="pydecimal",
                        type="float",
                        constraint=ConstraintConfig(min=-500, max=500, right_digits=2),
                    ),
                    FieldDefinition(
                        name="posting_date",
                        generator="date_between",
                        type="date",
                        constraint=ConstraintConfig(start="-6d", end="today"),
                    ),
                    FieldDefinition(
                        name="currency",
                        generator="currency_code",
                        type="string",
                    ),
                    FieldDefinition(
                        name="txn_type",
                        generator="random_element",
                        type="string",
                        constraint=ConstraintConfig(values="Credit,Debit"),
                    ),
                ],
            )
        ],
        homogeneity=100,
        seed=seed,
        reconciliation_mode=True,
        balances=[balance] if balance else [],
    )


def _fetch_balance(db, table_name: str) -> list[list]:
    rows = db.execute(f'SELECT * FROM "{table_name}" ORDER BY partition_date, account').fetchall()
    return [list(r) for r in rows]


def test_balance_requires_reconciliation_mode(db):
    balance = BalanceConfig(
        name="balances",
        source_dataset="txns",
        date_field="posting_date",
        amount_field="amount",
        group_by=["account"],
    )
    req = _txn_request(balance=balance)
    req.reconciliation_mode = False
    with pytest.raises(ValueError, match="balance"):
        generate_datasets(req)


def test_balance_source_must_exist(db):
    balance = BalanceConfig(
        name="balances",
        source_dataset="missing",
        date_field="posting_date",
        amount_field="amount",
        group_by=["account"],
    )
    with pytest.raises(ValueError, match="not part of this run"):
        generate_datasets(_txn_request(balance=balance))


def test_balance_scaling_rule_enforced(db):
    balance = BalanceConfig(
        name="balances",
        source_dataset="txns",
        date_field="posting_date",
        amount_field="amount",
        group_by=["account"],
        days=5,
        records_per_day=10,
    )
    with pytest.raises(ValueError, match="days × records_per_day"):
        generate_datasets(_txn_request(rows=40, balance=balance))


def test_balance_scaling_rule_satisfied(db):
    balance = BalanceConfig(
        name="balances",
        source_dataset="txns",
        date_field="posting_date",
        amount_field="amount",
        group_by=["account"],
        days=5,
        records_per_day=10,
    )
    resp = generate_datasets(_txn_request(rows=50, balance=balance))
    balance_result = resp.datasets[1]
    assert balance_result.name == "balances"
    assert balance_result.columns == _BALANCE_COLUMNS


def test_balance_non_numeric_amount_rejected(db):
    balance = BalanceConfig(
        name="balances",
        source_dataset="txns",
        date_field="posting_date",
        amount_field="account",
        group_by=["account"],
    )
    with pytest.raises(ValueError, match="must be numeric"):
        generate_datasets(_txn_request(balance=balance))


def test_balance_date_field_rejected(db):
    balance = BalanceConfig(
        name="balances",
        source_dataset="txns",
        date_field="account",
        amount_field="amount",
        group_by=["account"],
    )
    with pytest.raises(ValueError, match="DATE or TIMESTAMP"):
        generate_datasets(_txn_request(balance=balance))


def test_balance_continuity_and_controls(db):
    balance = BalanceConfig(
        name="balances",
        source_dataset="txns",
        date_field="posting_date",
        amount_field="amount",
        group_by=["account"],
        opening_balance=100.0,
    )
    resp = generate_datasets(_txn_request(rows=200, seed=7, balance=balance))
    balance_result = resp.datasets[1]
    rows = _fetch_balance(db, balance_result.table_name)
    assert len(rows) > 0
    assert len(rows) == balance_result.row_count

    opening: dict[str, float] = {}
    for row in rows:
        date, account, opening_bal, sum_pos, sum_neg, closing, count = row
        expected_open = opening.get(account, 100.0)
        assert abs(float(opening_bal) - expected_open) < 1e-9
        assert abs(float(closing) - (float(opening_bal) + float(sum_pos) + float(sum_neg))) < 1e-9
        opening[account] = float(closing)


def test_balance_sign_field_maps_positives(db):
    balance = BalanceConfig(
        name="balances",
        source_dataset="txns",
        date_field="posting_date",
        amount_field="amount",
        group_by=["account"],
        sign_field="txn_type",
        positive_values=["Credit"],
        opening_balance=0.0,
    )
    resp = generate_datasets(_txn_request(rows=200, seed=9, balance=balance))
    balance_result = resp.datasets[1]
    rows = _fetch_balance(db, balance_result.table_name)
    source_rows = db.execute(f'SELECT "amount", "txn_type" FROM "dataset_{resp.datasets[0].dataset_id}"').fetchall()
    signed_source_sum = 0.0
    for amount, txn_type in source_rows:
        amount = float(amount)
        signed_source_sum += amount if txn_type == "Credit" else -amount

    balance_total_delta = sum(
        float(r[3]) + float(r[4]) for r in rows  # sum_positives + sum_negatives
    )
    assert abs(signed_source_sum - balance_total_delta) < 1e-6


def test_continuity_rows_multikey():
    agg = [
        ["2026-01-01", "A", "USD", 25.0, -15.0, 50],
        ["2026-01-02", "A", "USD", 120.0, -29.0, 85],
        ["2026-01-02", "B", "USD", 10.0, 0.0, 3],
    ]
    rows = _continuity_rows(agg, num_group_cols=2, opening_balance=None)
    assert rows[0][3:] == [0.0, 25.0, -15.0, 10.0, 50]
    assert rows[1][3:] == [10.0, 120.0, -29.0, 101.0, 85]
    assert rows[2][3:] == [0.0, 10.0, 0.0, 10.0, 3]


def test_continuity_rows_custom_opening():
    agg = [["2026-01-01", 30.0, -5.0, 10]]
    rows = _continuity_rows(agg, num_group_cols=0, opening_balance=50.0)
    assert rows[0][1:] == [50.0, 30.0, -5.0, 75.0, 10]


def test_build_balance_sql_default_sign():
    cfg = BalanceConfig(
        name="b",
        source_dataset="txns",
        date_field="posting_date",
        amount_field="amount",
        group_by=["account"],
    )
    sql = build_balance_sql("dataset_x", cfg, {"account": "VARCHAR", "posting_date": "DATE", "amount": "DOUBLE"})
    assert '"amount" AS sgn' in sql


def test_build_balance_sql_sign_field():
    cfg = BalanceConfig(
        name="b",
        source_dataset="txns",
        date_field="posting_date",
        amount_field="amount",
        group_by=["account"],
        sign_field="txn_type",
        positive_values=["Credit", "Deposit"],
    )
    sql = build_balance_sql("dataset_x", cfg, {"posting_date": "DATE", "amount": "DOUBLE", "account": "VARCHAR", "txn_type": "VARCHAR"})
    assert "CASE WHEN" in sql