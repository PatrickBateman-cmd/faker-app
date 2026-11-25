from __future__ import annotations

from app.schemas.generation import (
    BalanceConfig,
    DatasetDefinition,
    FieldBreakConfig,
    GenerateRequest,
    GenerateResponse,
    ReconBreakRecord,
)


def test_generate_request_defaults_are_backward_compatible():
    req = GenerateRequest(datasets=[DatasetDefinition(name="test")])
    assert req.reconciliation_mode is False
    assert req.field_breaks == []
    assert req.balances == []


def test_field_break_config_defaults():
    cfg = FieldBreakConfig(field_name="amount")
    assert cfg.break_rate == 0.0
    assert cfg.break_style == "drift"
    assert cfg.drift_pct == 0.02


def test_generate_response_break_count_defaults_zero():
    resp = GenerateResponse(run_id=1, homogeneity=50, seed=None, datasets=[])
    assert resp.break_count == 0


def test_recon_break_record_round_trip():
    rec = ReconBreakRecord(
        id=1,
        run_id=1,
        dataset_id="abc",
        field_name="amount",
        join_key_value="T1",
        true_value="100.0",
        broken_value="105.0",
        break_style="drift",
        created_at="2026-09-01T00:00:00",
    )
    assert rec.field_name == "amount"


def test_balance_config_defaults():
    cfg = BalanceConfig(name="balances", source_dataset="txns", date_field="posting_date", amount_field="amount")
    assert cfg.group_by == []
    assert cfg.opening_balance is None
    assert cfg.days is None
    assert cfg.records_per_day is None
    assert cfg.sign_field is None
    assert cfg.positive_values == []
