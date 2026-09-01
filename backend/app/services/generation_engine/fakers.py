from __future__ import annotations

import random

from faker import Faker

from app.schemas.generation import FieldDefinition


def build_field_fakers(
    fields: list[FieldDefinition],
    homogeneity: int,
    master_seed: int,
    namespace: str = "",
) -> list[Faker | None]:
    result: list[Faker | None] = []
    for field in fields:
        if field.generator in ("shared_key", "formula", "uuid4", "uuid_int"):
            result.append(None)
            continue
        seed_roll = random.randint(1, 100)
        use_master = seed_roll <= homogeneity
        if use_master:
            field_seed = (master_seed + hash(f"{namespace}{field.name}")) % (10**9)
            fk = Faker()
            fk.seed_instance(field_seed)
            result.append(fk)
        else:
            result.append(None)
    return result
