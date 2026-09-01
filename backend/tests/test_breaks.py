from __future__ import annotations

import random

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
