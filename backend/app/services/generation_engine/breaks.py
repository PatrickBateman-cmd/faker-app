from __future__ import annotations

import random
from dataclasses import dataclass

from faker import Faker

from app.schemas.generation import FieldBreakConfig, FieldDefinition
from app.services.generation_engine.generators import generate_field_value


@dataclass
class BreakRecord:
    dataset_id: str
    field_name: str
    join_key_value: object
    true_value: object
    broken_value: object
    break_style: str


def _transform(true_value: object, field: FieldDefinition, cfg: FieldBreakConfig, fake: Faker) -> object:
    if cfg.break_style == "null":
        return None
    if cfg.break_style == "drift":
        delta = true_value * cfg.drift_pct * random.uniform(-1.0, 1.0)
        drifted = true_value + delta
        return round(drifted, 6) if isinstance(true_value, float) else int(round(drifted))
    return generate_field_value(fake, field, field.constraint)


def apply_field_breaks(
    row: list,
    fields: list[FieldDefinition],
    field_breaks: dict[str, FieldBreakConfig],
    join_key_value: object,
    dataset_id: str,
    fake: Faker,
) -> list[BreakRecord]:
    breaks: list[BreakRecord] = []
    for fi, field in enumerate(fields):
        cfg = field_breaks.get(field.name)
        if cfg is None or random.random() >= cfg.break_rate:
            continue
        true_value = row[fi]
        row[fi] = _transform(true_value, field, cfg, fake)
        breaks.append(
            BreakRecord(
                dataset_id=dataset_id,
                field_name=field.name,
                join_key_value=join_key_value,
                true_value=true_value,
                broken_value=row[fi],
                break_style=cfg.break_style,
            )
        )
    return breaks
