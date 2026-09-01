from __future__ import annotations

import logging
import random

from faker import Faker
from jinja2 import Template as JinjaTemplate

from app.schemas.generation import FieldDefinition
from app.services.generation_engine.conditions import check_condition
from app.services.generation_engine.generators import generate_field_value

logger = logging.getLogger(__name__)


def generate_row(
    fields: list[FieldDefinition],
    fakers: list[Faker | None],
    fake_fallback: Faker,
    pool_entry: dict | None = None,
    shared_key_pool: list | None = None,
) -> list:
    row = []
    pool_entry = pool_entry or {}
    for fi, field in enumerate(fields):
        if field.name in pool_entry:
            row.append(pool_entry[field.name])
            continue

        if field.null_probability and random.random() < field.null_probability:
            row.append(None)
            continue

        if field.condition:
            if not check_condition(field.condition, row, fields):
                row.append(None)
                continue

        if field.generator == "shared_key" and shared_key_pool is not None:
            val = random.choice(shared_key_pool) if shared_key_pool else None
            row.append(val)
            continue

        if field.generator == "formula":
            try:
                t = JinjaTemplate(field.formula or "")
                already = {f.name: row[idx] for idx, f in enumerate(fields[:fi])}
                row.append(t.render(**already))
            except Exception:
                logger.exception("Formula evaluation failed for field '%s'", field.name)
                row.append(field.formula or "")
            continue

        fk = fakers[fi] or fake_fallback
        row.append(generate_field_value(fk, field, None))
    return row
