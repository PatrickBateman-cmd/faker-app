from __future__ import annotations

import json

from typer.testing import CliRunner

from app.schemas.generation import (
    ConstraintConfig,
    DatasetDefinition,
    FieldDefinition,
    GenerateRequest,
)
from app.services.generation_engine import generate_datasets
from cli.main import app

runner = CliRunner()


def _generate_txn_dataset(db, rows: int = 5) -> str:
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(
                name="txns",
                rows=rows,
                fields=[
                    FieldDefinition(
                        name="account_id", generator="bothify", type="string",
                        constraint=ConstraintConfig(format="ACC-##"),
                    ),
                    FieldDefinition(
                        name="currency", generator="random_element", type="string",
                        constraint=ConstraintConfig(values="USD"),
                    ),
                    FieldDefinition(name="amount", generator="random_int", type="integer"),
                    FieldDefinition(
                        name="transaction_type", generator="random_element", type="string",
                        constraint=ConstraintConfig(values="Credit,Debit"),
                    ),
                    FieldDefinition(
                        name="transaction_date", generator="date_between", type="date",
                        constraint=ConstraintConfig(start="-3d", end="today"),
                    ),
                ],
            )
        ],
        homogeneity=100,
        seed=5,
    )
    return generate_datasets(req).datasets[0].dataset_id


def test_cli_balance_derive_happy_path(db):
    ds_id = _generate_txn_dataset(db)

    result = runner.invoke(
        app,
        [
            "balance", "derive", ds_id,
            "--name", "cli_balances",
            "--account-fields", "account_id",
            "--format", "json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["transform_type"] == "balance"
    assert payload["row_count"] > 0
    assert "opening_balance_seed" in payload


def test_cli_balance_derive_opening_balance_seed_round_trip(db):
    ledger_id = _generate_txn_dataset(db)
    street_id = _generate_txn_dataset(db)

    first = runner.invoke(
        app,
        [
            "balance", "derive", ledger_id,
            "--name", "ledger_balances",
            "--account-fields", "account_id",
            "--format", "json",
        ],
    )
    assert first.exit_code == 0, first.output
    seed = json.loads(first.output)["opening_balance_seed"]

    second = runner.invoke(
        app,
        [
            "balance", "derive", street_id,
            "--name", "street_balances",
            "--account-fields", "account_id",
            "--opening-balance-seed", str(seed),
            "--format", "json",
        ],
    )
    assert second.exit_code == 0, second.output
    assert json.loads(second.output)["opening_balance_seed"] == seed


def test_cli_balance_derive_with_breaks(db):
    ds_id = _generate_txn_dataset(db)

    result = runner.invoke(
        app,
        [
            "balance", "derive", ds_id,
            "--name", "broken_balances",
            "--account-fields", "account_id",
            "--balance-breaks-json",
            json.dumps([{"field_name": "closing_balance", "break_rate": 1.0, "break_style": "drift"}]),
            "--format", "json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["break_count"] == payload["row_count"]
    assert payload["run_id"] is not None


def test_cli_balance_derive_rejects_unknown_dataset(db):
    result = runner.invoke(
        app,
        ["balance", "derive", "nonexistent", "--name", "x", "--account-fields", "account_id"],
    )
    assert result.exit_code == 1
