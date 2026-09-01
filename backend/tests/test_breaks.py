from __future__ import annotations

import random

import pytest
from faker import Faker

from app.schemas.generation import FieldBreakConfig, FieldDefinition
from app.services.generation_engine.breaks import BreakRecord, apply_field_breaks


def _fields():
    return [
        FieldDefinition(name="trade_id", generator="uuid4", type="string"),
        FieldDefinition(name="amount", generator="pydecimal", type="float"),
        FieldDefinition(name="status", generator="random_element", type="string"),
    ]


def test_break_rate_zero_never_fires():
    random.seed(1)
    fake = Faker()
    fake.seed_instance(1)
    fields = _fields()
    row = ["T1", 1000.0, "settled"]
    breaks = apply_field_breaks(
        row, fields, {"amount": FieldBreakConfig(field_name="amount", break_rate=0.0)},
        join_key_value="T1", dataset_id="ds-1", fake=fake,
    )
    assert breaks == []
    assert row == ["T1", 1000.0, "settled"]


def test_break_rate_one_always_fires_and_records():
    random.seed(1)
    fake = Faker()
    fake.seed_instance(1)
    fields = _fields()
    row = ["T1", 1000.0, "settled"]
    breaks = apply_field_breaks(
        row, fields,
        {"amount": FieldBreakConfig(field_name="amount", break_rate=1.0, break_style="drift", drift_pct=0.1)},
        join_key_value="T1", dataset_id="ds-1", fake=fake,
    )
    assert len(breaks) == 1
    rec = breaks[0]
    assert isinstance(rec, BreakRecord)
    assert rec.field_name == "amount"
    assert rec.dataset_id == "ds-1"
    assert rec.join_key_value == "T1"
    assert rec.true_value == 1000.0
    assert rec.broken_value == row[1]
    assert abs(row[1] - 1000.0) <= 1000.0 * 0.1 + 1e-6


def test_break_style_null_sets_none():
    random.seed(1)
    fake = Faker()
    fake.seed_instance(1)
    fields = _fields()
    row = ["T1", 1000.0, "settled"]
    breaks = apply_field_breaks(
        row, fields, {"amount": FieldBreakConfig(field_name="amount", break_rate=1.0, break_style="null")},
        join_key_value="T1", dataset_id="ds-1", fake=fake,
    )
    assert breaks[0].broken_value is None
    assert row[1] is None


def test_only_configured_fields_are_eligible():
    random.seed(1)
    fake = Faker()
    fake.seed_instance(1)
    fields = _fields()
    row = ["T1", 1000.0, "settled"]
    breaks = apply_field_breaks(
        row, fields, {"status": FieldBreakConfig(field_name="status", break_rate=1.0, break_style="null")},
        join_key_value="T1", dataset_id="ds-1", fake=fake,
    )
    assert len(breaks) == 1
    assert breaks[0].field_name == "status"
    assert row[1] == 1000.0  # amount untouched
    assert row[2] is None


# --- Finding 1: drift on small/zero integers must never round back to true_value ---


def test_drift_break_on_small_integer_always_differs_from_true_value():
    fields = [FieldDefinition(name="score", generator="random_int", type="integer")]
    cfg = {"score": FieldBreakConfig(field_name="score", break_rate=1.0, break_style="drift", drift_pct=0.02)}
    # At the default drift_pct=0.02, |value| < 25 previously rounded right back to itself.
    for trial_seed in range(50):
        random.seed(trial_seed)
        row = [10]
        breaks = apply_field_breaks(row, fields, cfg, join_key_value="K1", dataset_id="ds-1", fake=Faker())
        assert len(breaks) == 1
        assert breaks[0].broken_value != breaks[0].true_value
        assert row[0] != 10


def test_drift_break_on_zero_integer_always_differs_from_true_value():
    fields = [FieldDefinition(name="score", generator="random_int", type="integer")]
    cfg = {"score": FieldBreakConfig(field_name="score", break_rate=1.0, break_style="drift", drift_pct=0.5)}
    for trial_seed in range(20):
        random.seed(trial_seed)
        row = [0]
        breaks = apply_field_breaks(row, fields, cfg, join_key_value="K1", dataset_id="ds-1", fake=Faker())
        assert len(breaks) == 1
        assert breaks[0].broken_value != 0
        assert row[0] != 0


def test_drift_break_on_zero_float_always_differs_from_true_value():
    fields = [FieldDefinition(name="amount", generator="pydecimal", type="float")]
    cfg = {"amount": FieldBreakConfig(field_name="amount", break_rate=1.0, break_style="drift", drift_pct=0.02)}
    for trial_seed in range(20):
        random.seed(trial_seed)
        row = [0.0]
        breaks = apply_field_breaks(row, fields, cfg, join_key_value="K1", dataset_id="ds-1", fake=Faker())
        assert len(breaks) == 1
        assert breaks[0].broken_value != 0.0
        assert row[0] != 0.0


# --- Finding 2: drift on a None true_value must not raise and must not record a break ---


@pytest.mark.parametrize("break_style", ["drift", "null", "different"])
def test_break_is_skipped_when_true_value_is_none(break_style):
    random.seed(1)
    fake = Faker()
    fake.seed_instance(1)
    fields = [FieldDefinition(name="amount", generator="random_int", type="integer")]
    row = [None]
    cfg = {"amount": FieldBreakConfig(field_name="amount", break_rate=1.0, break_style=break_style)}
    # Must not raise TypeError, and must not record a phantom None -> None "break".
    breaks = apply_field_breaks(row, fields, cfg, join_key_value="K1", dataset_id="ds-1", fake=fake)
    assert breaks == []
    assert row == [None]


# --- Finding 3: int-vs-float rounding must follow field.type, not isinstance(true_value) ---


def test_drift_break_broken_value_type_follows_declared_field_type_not_runtime_type():
    fields = [FieldDefinition(name="score", generator="random_int", type="integer")]
    # Simulate apply_constraint() handing back a float for a field declared "integer"
    # (e.g. a float min/max clamp) -- the recorded ground truth must still round to int
    # because DuckDB stores this column as BIGINT.
    random.seed(1)
    row = [1.5]
    cfg = {"score": FieldBreakConfig(field_name="score", break_rate=1.0, break_style="drift", drift_pct=0.02)}
    breaks = apply_field_breaks(row, fields, cfg, join_key_value="K1", dataset_id="ds-1", fake=Faker())
    assert len(breaks) == 1
    assert isinstance(breaks[0].broken_value, int)
    assert isinstance(row[0], int)
