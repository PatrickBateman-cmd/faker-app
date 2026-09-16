from __future__ import annotations

from faker import Faker

from app.schemas.generation import DatasetDefinition, FieldDefinition
from app.services.generation_engine.generators import generate_field_value


def effective_fields(ds: DatasetDefinition) -> list[FieldDefinition]:
    if ds.group_config:
        return ds.group_config.parent_fields + ds.group_config.child_fields
    return ds.fields


def build_overlap_pool(
    fake: Faker,
    fields: list[FieldDefinition],
    exact_field_names: set[str],
    pool_size: int,
) -> list[dict]:
    exact_fields = [f for f in fields if f.name in exact_field_names]
    pool = []
    for _ in range(pool_size):
        entry = {}
        for field in exact_fields:
            entry[field.name] = generate_field_value(fake, field, None)
        pool.append(entry)
    return pool


def build_parent_pool(
    fake: Faker,
    parent_fields: list[FieldDefinition],
    join_key_field: str,
    num_groups: int,
) -> list[dict]:
    field = next(f for f in parent_fields if f.name == join_key_field)
    return [{field.name: generate_field_value(fake, field, None)} for _ in range(num_groups)]
