from __future__ import annotations

import json
import uuid

import pytest

from app.core.database import DuckDBManager
from app.schemas.balance import BalanceDeriveRequest
from app.schemas.generation import (
    ConstraintConfig,
    DatasetDefinition,
    FieldBreakConfig,
    FieldDefinition,
    GenerateRequest,
    GroupConfig,
)
from app.services.balance_service import derive_balances
from app.services.dataset_service import get_dataset
from app.services.generation_engine import generate_datasets


def _register_raw_dataset(db, name: str, columns: list[tuple[str, str]], rows: list[tuple]) -> str:
    dataset_id = str(uuid.uuid4())
    table_name = f"dataset_{dataset_id}"
    col_defs = ", ".join(f'"{c}" {t}' for c, t in columns)
    db.execute(f'CREATE TABLE "{table_name}" ({col_defs})')
    if rows:
        placeholders = ", ".join(["?"] * len(columns))
        db.executemany(f'INSERT INTO "{table_name}" VALUES ({placeholders})', [list(r) for r in rows])
    col_names = [c for c, _ in columns]
    db.execute(
        """
        INSERT INTO metadata_datasets (dataset_id, run_id, name, table_name, columns_json, row_count, homogeneity, seed)
        VALUES (?, NULL, ?, ?, ?, ?, NULL, NULL)
        """,
        [dataset_id, name, table_name, json.dumps(col_names), len(rows)],
    )
    return dataset_id


_TXN_COLUMNS = [
    ("entity_id", "VARCHAR"),
    ("sub_account_id", "VARCHAR"),
    ("currency", "VARCHAR"),
    ("transaction_date", "DATE"),
    ("amount", "DOUBLE"),
    ("transaction_type", "VARCHAR"),
]


def _fetch_dicts(table_name: str) -> list[dict]:
    db = DuckDBManager.get_instance()
    cols = [d[0] for d in db.execute(f'SELECT * FROM "{table_name}" LIMIT 0').description]
    rows = db.execute(f'SELECT * FROM "{table_name}" ORDER BY day').fetchall()
    return [dict(zip(cols, r, strict=True)) for r in rows]


def _txn_dataset_def(name: str, num_groups: int = 3, rows: int = 60) -> DatasetDefinition:
    return DatasetDefinition(
        name=name,
        rows=rows,
        group_config=GroupConfig(
            num_groups=num_groups,
            split_pct=100,
            parent_fields=[
                FieldDefinition(
                    name="sub_account_id",
                    generator="bothify",
                    type="string",
                    constraint=ConstraintConfig(format="SUB-????????"),
                ),
                FieldDefinition(
                    name="ledger_account_id",
                    generator="formula",
                    type="string",
                    formula="LDG-{{ sub_account_id[4:6] }}",
                ),
                FieldDefinition(
                    name="entity_id",
                    generator="formula",
                    type="string",
                    formula="ENT-{{ sub_account_id[4:5] }}",
                ),
            ],
            child_fields=[
                FieldDefinition(name="transaction_id", generator="uuid4", type="string", unique=True),
                FieldDefinition(
                    name="amount",
                    generator="pydecimal",
                    type="float",
                    constraint=ConstraintConfig(min=1, max=1000, right_digits=2),
                ),
                FieldDefinition(
                    name="currency",
                    generator="random_element",
                    type="string",
                    constraint=ConstraintConfig(values="USD"),
                ),
                FieldDefinition(
                    name="transaction_type",
                    generator="random_element",
                    type="string",
                    constraint=ConstraintConfig(values="Credit,Debit"),
                ),
                FieldDefinition(
                    name="transaction_date",
                    generator="date_between",
                    type="date",
                    constraint=ConstraintConfig(start="-4d", end="today"),
                ),
            ],
        ),
    )


def _generate_pair(db, num_groups: int = 3, rows: int = 60, seed: int = 42) -> tuple[str, str]:
    req = GenerateRequest(
        datasets=[_txn_dataset_def("ledger", num_groups, rows), _txn_dataset_def("street", num_groups, rows)],
        homogeneity=100,
        seed=seed,
        reconciliation_mode=True,
        exact_fields=["sub_account_id", "currency", "amount", "transaction_date"],
    )
    resp = generate_datasets(req)
    return resp.datasets[0].dataset_id, resp.datasets[1].dataset_id


def test_date_spine_includes_zero_activity_days(db):
    rows = [
        ("ENT-1", "SUB-1", "USD", "2026-01-01", 100.0, "Credit"),
        ("ENT-1", "SUB-1", "USD", "2026-01-03", 50.0, "Debit"),
    ]
    ds_id = _register_raw_dataset(db, "txns", _TXN_COLUMNS, rows)

    result = derive_balances(
        ds_id,
        BalanceDeriveRequest(
            name="balances",
            account_fields=["entity_id", "sub_account_id"],
            start_date="2026-01-01",
            end_date="2026-01-05",
            opening_balance_seed=0.0,
        ),
    )
    assert result.row_count == 5

    data = _fetch_dicts(result.table_name)
    net_by_day = {str(r["day"]): r["net_movement"] for r in data}
    assert len(net_by_day) == 5
    assert net_by_day["2026-01-02"] == 0.0
    assert net_by_day["2026-01-04"] == 0.0
    assert net_by_day["2026-01-05"] == 0.0
    assert net_by_day["2026-01-01"] == 100.0
    assert net_by_day["2026-01-03"] == -50.0


def test_carry_forward_and_closing_equals_opening_plus_net(db):
    rows = [
        ("ENT-1", "SUB-1", "USD", "2026-01-01", 100.0, "Credit"),
        ("ENT-1", "SUB-1", "USD", "2026-01-01", 20.0, "Debit"),
        ("ENT-1", "SUB-1", "USD", "2026-01-03", 30.0, "Credit"),
    ]
    ds_id = _register_raw_dataset(db, "txns", _TXN_COLUMNS, rows)

    result = derive_balances(
        ds_id,
        BalanceDeriveRequest(
            name="bal",
            account_fields=["entity_id", "sub_account_id"],
            start_date="2026-01-01",
            end_date="2026-01-03",
            opening_balance_seed=1000.0,
        ),
    )
    data = _fetch_dicts(result.table_name)
    assert len(data) == 3

    assert data[0]["opening_balance"] == 1000.0
    assert data[0]["net_movement"] == 80.0
    assert data[0]["closing_balance"] == 1080.0

    assert data[1]["opening_balance"] == data[0]["closing_balance"]
    assert data[1]["net_movement"] == 0.0

    assert data[2]["opening_balance"] == data[1]["closing_balance"]
    assert data[2]["net_movement"] == 30.0
    assert data[2]["closing_balance"] == 1110.0

    for r in data:
        assert abs(r["closing_balance"] - (r["opening_balance"] + r["net_movement"])) < 1e-6


def test_account_only_gets_spine_for_currencies_it_used(db):
    rows = [
        ("ENT-1", "SUB-1", "USD", "2026-01-01", 100.0, "Credit"),
        ("ENT-2", "SUB-2", "EUR", "2026-01-01", 50.0, "Credit"),
    ]
    ds_id = _register_raw_dataset(db, "txns", _TXN_COLUMNS, rows)

    result = derive_balances(
        ds_id,
        BalanceDeriveRequest(
            name="bal",
            account_fields=["entity_id", "sub_account_id"],
            start_date="2026-01-01",
            end_date="2026-01-02",
            opening_balance_seed=0.0,
        ),
    )
    data = _fetch_dicts(result.table_name)
    assert len(data) == 4  # 2 accounts x 2 days, NOT 2 accounts x 2 currencies x 2 days

    sub1_currencies = {r["currency"] for r in data if r["sub_account_id"] == "SUB-1"}
    sub2_currencies = {r["currency"] for r in data if r["sub_account_id"] == "SUB-2"}
    assert sub1_currencies == {"USD"}
    assert sub2_currencies == {"EUR"}


def test_opening_balance_seed_returned_and_reusable(db):
    rows = [("ENT-1", "SUB-1", "USD", "2026-01-01", 100.0, "Credit")]
    ds_id = _register_raw_dataset(db, "txns", _TXN_COLUMNS, rows)

    r1 = derive_balances(
        ds_id, BalanceDeriveRequest(name="b1", account_fields=["entity_id", "sub_account_id"])
    )
    r2 = derive_balances(
        ds_id, BalanceDeriveRequest(name="b2", account_fields=["entity_id", "sub_account_id"])
    )
    assert r1.opening_balance_seed != r2.opening_balance_seed

    assert _fetch_dicts(r1.table_name)[0]["opening_balance"] == r1.opening_balance_seed
    assert _fetch_dicts(r2.table_name)[0]["opening_balance"] == r2.opening_balance_seed


def test_same_seed_across_ledger_and_street_yields_identical_day1_opening(db):
    ledger_id, street_id = _generate_pair(db)

    ledger_bal = derive_balances(
        ledger_id,
        BalanceDeriveRequest(name="ledger_bal", account_fields=["entity_id", "ledger_account_id", "sub_account_id"]),
    )
    street_bal = derive_balances(
        street_id,
        BalanceDeriveRequest(
            name="street_bal",
            account_fields=["entity_id", "ledger_account_id", "sub_account_id"],
            opening_balance_seed=ledger_bal.opening_balance_seed,
            start_date=ledger_bal.start_date,
            end_date=ledger_bal.end_date,
        ),
    )
    assert street_bal.opening_balance_seed == ledger_bal.opening_balance_seed

    ledger_day1 = [r for r in _fetch_dicts(ledger_bal.table_name) if str(r["day"]) == ledger_bal.start_date]
    street_day1 = [r for r in _fetch_dicts(street_bal.table_name) if str(r["day"]) == street_bal.start_date]
    assert ledger_day1 and street_day1
    assert all(r["opening_balance"] == ledger_bal.opening_balance_seed for r in ledger_day1)
    assert all(r["opening_balance"] == ledger_bal.opening_balance_seed for r in street_day1)


def test_hierarchy_consistent_across_ledger_and_street(db):
    ledger_id, street_id = _generate_pair(db)
    ledger_table = get_dataset(ledger_id)["table_name"]
    street_table = get_dataset(street_id)["table_name"]

    db_mgr = DuckDBManager.get_instance()
    ledger_combos = set(
        db_mgr.execute(
            f'SELECT DISTINCT sub_account_id, ledger_account_id, entity_id FROM "{ledger_table}"'
        ).fetchall()
    )
    street_combos = set(
        db_mgr.execute(
            f'SELECT DISTINCT sub_account_id, ledger_account_id, entity_id FROM "{street_table}"'
        ).fetchall()
    )
    assert ledger_combos == street_combos
    assert len(ledger_combos) > 0


def test_balance_break_ground_truth_matches_run_id(db):
    rows = [
        ("ENT-1", "SUB-1", "USD", "2026-01-01", 100.0, "Credit"),
        ("ENT-1", "SUB-1", "USD", "2026-01-02", 20.0, "Credit"),
    ]
    ds_id = _register_raw_dataset(db, "txns", _TXN_COLUMNS, rows)

    result = derive_balances(
        ds_id,
        BalanceDeriveRequest(
            name="bal",
            account_fields=["entity_id", "sub_account_id"],
            start_date="2026-01-01",
            end_date="2026-01-02",
            opening_balance_seed=0.0,
            balance_breaks=[
                FieldBreakConfig(field_name="closing_balance", break_rate=1.0, break_style="drift", drift_pct=0.05)
            ],
        ),
    )
    assert result.break_count == result.row_count == 2
    assert result.run_id is not None

    gt = db.execute(
        "SELECT join_key_value, true_value, broken_value FROM metadata_recon_breaks WHERE run_id = ?",
        [result.run_id],
    ).fetchall()
    assert len(gt) == 2
    for jk, tv, bv in gt:
        assert jk is not None
        assert tv != bv


def test_balance_break_does_not_cascade(db):
    rows = [
        ("ENT-1", "SUB-1", "USD", "2026-01-01", 100.0, "Credit"),
        ("ENT-1", "SUB-1", "USD", "2026-01-02", 10.0, "Credit"),
    ]
    ds_id = _register_raw_dataset(db, "txns", _TXN_COLUMNS, rows)

    result = derive_balances(
        ds_id,
        BalanceDeriveRequest(
            name="bal",
            account_fields=["entity_id", "sub_account_id"],
            start_date="2026-01-01",
            end_date="2026-01-02",
            opening_balance_seed=0.0,
            balance_breaks=[
                FieldBreakConfig(field_name="closing_balance", break_rate=1.0, break_style="drift", drift_pct=0.5)
            ],
        ),
    )
    data = _fetch_dicts(result.table_name)
    day1, day2 = data[0], data[1]
    assert str(day1["day"]) == "2026-01-01"
    assert str(day2["day"]) == "2026-01-02"

    gt_rows = db.execute(
        "SELECT join_key_value, true_value FROM metadata_recon_breaks WHERE run_id = ?",
        [result.run_id],
    ).fetchall()
    day1_true_closing = next(float(tv) for jk, tv in gt_rows if jk.endswith("2026-01-01"))

    assert day1["closing_balance"] != day1_true_closing  # actually broken
    assert day2["opening_balance"] == day1_true_closing  # but the true value carried forward


def test_balance_break_null_style(db):
    rows = [("ENT-1", "SUB-1", "USD", "2026-01-01", 100.0, "Credit")]
    ds_id = _register_raw_dataset(db, "txns", _TXN_COLUMNS, rows)

    result = derive_balances(
        ds_id,
        BalanceDeriveRequest(
            name="bal",
            account_fields=["entity_id", "sub_account_id"],
            start_date="2026-01-01",
            end_date="2026-01-01",
            opening_balance_seed=0.0,
            balance_breaks=[FieldBreakConfig(field_name="closing_balance", break_rate=1.0, break_style="null")],
        ),
    )
    data = _fetch_dicts(result.table_name)
    assert data[0]["closing_balance"] is None

    gt = db.execute(
        "SELECT true_value, broken_value FROM metadata_recon_breaks WHERE run_id = ?", [result.run_id]
    ).fetchall()
    assert gt[0][1] is None
    assert gt[0][0] is not None


def test_derive_balances_rejects_unknown_source_dataset(db):
    with pytest.raises(LookupError, match="not found"):
        derive_balances("nonexistent", BalanceDeriveRequest(name="x", account_fields=["entity_id"]))


def test_derive_balances_rejects_invalid_column_name(db):
    rows = [("ENT-1", "SUB-1", "USD", "2026-01-01", 10.0, "Credit")]
    ds_id = _register_raw_dataset(db, "txns", _TXN_COLUMNS, rows)
    with pytest.raises(ValueError, match="Invalid column name"):
        derive_balances(ds_id, BalanceDeriveRequest(name="x", account_fields=["entity_id; DROP TABLE x"]))


def test_derive_balances_rejects_invalid_balance_break_field(db):
    rows = [("ENT-1", "SUB-1", "USD", "2026-01-01", 10.0, "Credit")]
    ds_id = _register_raw_dataset(db, "txns", _TXN_COLUMNS, rows)
    with pytest.raises(ValueError, match="must be one of"):
        derive_balances(
            ds_id,
            BalanceDeriveRequest(
                name="x",
                account_fields=["entity_id", "sub_account_id"],
                balance_breaks=[FieldBreakConfig(field_name="amount", break_rate=1.0, break_style="null")],
            ),
        )
