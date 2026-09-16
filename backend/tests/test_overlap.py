from __future__ import annotations

from faker import Faker

from app.schemas.generation import FieldDefinition
from app.services.generation_engine.overlap import build_parent_pool


def test_build_parent_pool_one_entry_per_group():
    fake = Faker()
    fake.seed_instance(42)
    parent_fields = [
        FieldDefinition(name="transaction_id", generator="uuid4", type="string"),
        FieldDefinition(name="other_parent_field", generator="word", type="string"),
    ]
    pool = build_parent_pool(fake, parent_fields, "transaction_id", num_groups=5)
    assert len(pool) == 5
    assert all(set(entry.keys()) == {"transaction_id"} for entry in pool)
    assert len({entry["transaction_id"] for entry in pool}) == 5  # uuid4 values are distinct


def test_build_parent_pool_zero_groups():
    fake = Faker()
    fake.seed_instance(1)
    parent_fields = [FieldDefinition(name="transaction_id", generator="uuid4", type="string")]
    pool = build_parent_pool(fake, parent_fields, "transaction_id", num_groups=0)
    assert pool == []
