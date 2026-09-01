from __future__ import annotations

import random

from faker import Faker

from app.schemas.generation import FieldDefinition


def roll_field_seeds(
    fields: list[FieldDefinition],
    homogeneity: int,
    master_seed: int,
    namespace: str = "",
) -> list[int | None]:
    seeds: list[int | None] = []
    for field in fields:
        if field.generator in ("shared_key", "formula", "uuid4", "uuid_int"):
            seeds.append(None)
            continue
        seed_roll = random.randint(1, 100)
        use_master = seed_roll <= homogeneity
        if use_master:
            seeds.append((master_seed + hash(f"{namespace}{field.name}")) % (10**9))
        else:
            seeds.append(None)
    return seeds


def fakers_from_seeds(seeds: list[int | None]) -> list[Faker | None]:
    result: list[Faker | None] = []
    for seed in seeds:
        if seed is None:
            result.append(None)
        else:
            fk = Faker()
            fk.seed_instance(seed)
            result.append(fk)
    return result


def build_field_fakers(
    fields: list[FieldDefinition],
    homogeneity: int,
    master_seed: int,
    namespace: str = "",
) -> list[Faker | None]:
    return fakers_from_seeds(roll_field_seeds(fields, homogeneity, master_seed, namespace))
