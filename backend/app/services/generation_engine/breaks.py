from __future__ import annotations

import random
from dataclasses import dataclass

from faker import Faker

from app.schemas.generation import FieldBreakConfig, FieldDefinition
from app.services.generation_engine.generators import generate_field_value

_INT_TYPES = {"integer", "int"}


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
        # Use the field's declared type (not the Python runtime type of true_value) to
        # decide int-vs-float rounding -- apply_constraint() can hand back a float for a
        # field declared "integer" (e.g. a float min/max clamp), and the recorded ground
        # truth must match what DuckDB actually stores for the column.
        is_int = field.type.lower() in _INT_TYPES
        draw = random.uniform(-1.0, 1.0)
        sign = 1 if draw >= 0 else -1

        if true_value == 0:
            # Multiplicative drift is always zero for a zero true_value regardless of
            # drift_pct; apply an absolute nudge instead so a break is still recorded.
            nudge = max(1, round(cfg.drift_pct * 100))
            drifted = sign * nudge
        else:
            delta = true_value * cfg.drift_pct * draw
            drifted = true_value + delta

        if is_int:
            result = int(round(drifted))
            if result == true_value:
                # At small |true_value| (e.g. |value| < 25 with the default drift_pct of
                # 0.02), rounding can land right back on true_value. A recorded break must
                # never equal the true value, so force a minimal +/-1 nudge.
                result = int(true_value) + sign
            return result

        result = round(float(drifted), 6)
        if result == true_value:
            # Extremely unlikely for a continuous float draw, but guard the invariant
            # anyway (e.g. random.uniform can return exactly 0.0).
            result = round(true_value + sign * max(abs(true_value) * cfg.drift_pct, 1e-6), 6)
        return result
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
        if true_value is None:
            # Nothing meaningful to drift/regenerate/null-out; a None -> None "break"
            # isn't a real break either, and drift's arithmetic would raise TypeError.
            continue
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
