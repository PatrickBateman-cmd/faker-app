from __future__ import annotations

import json
import random
import re
import uuid
from datetime import datetime, timedelta

from jinja2 import Template as JinjaTemplate

from faker import Faker

from app.core.database import DuckDBManager
from app.core.validation import validate_column_name, validate_table_name
from app.schemas.generation import (
    ConstraintConfig,
    DatasetDefinition,
    DatasetResult,
    FieldDefinition,
    GenerateRequest,
    GenerateResponse,
)


def _check_condition(condition: str, row: list, fields: list) -> bool:
    if not condition:
        return True
    m = re.match(r'^\s*(\w+)\s*(>=|<=|!=|==|>|<)\s*(.+)\s*$', condition)
    if not m:
        return True
    field_name, op, raw_val = m.group(1), m.group(2), m.group(3).strip()

    field_indices = {f.name: i for i, f in enumerate(fields)}
    if field_name not in field_indices:
        return True

    field_val = row[field_indices[field_name]]
    if field_val is None:
        return False

    try:
        val = int(raw_val) if raw_val.isdigit() else (float(raw_val) if '.' in raw_val else raw_val.strip('"').strip("'"))
    except ValueError:
        val = raw_val.strip('"').strip("'")

    if op == ">=":
        return field_val >= val
    elif op == "<=":
        return field_val <= val
    elif op == ">":
        return field_val > val
    elif op == "<":
        return field_val < val
    elif op == "==":
        return field_val == val
    elif op == "!=":
        return field_val != val
    return True


def _apply_constraint(fake: Faker, value: object, constraint: ConstraintConfig | None) -> object:
    if constraint is None:
        return value
    if isinstance(value, (int, float)):
        cmin = constraint.min if constraint.min is not None else float("-inf")
        cmax = constraint.max if constraint.max is not None else float("inf")
        if isinstance(value, float) and constraint.right_digits is not None:
            value = round(value, constraint.right_digits)
        return max(cmin, min(cmax, value))
    return value


def _generate_field_value(fake: Faker, field: FieldDefinition, constraint: ConstraintConfig | None) -> object:
    gen = field.generator
    cons = constraint or field.constraint

    if gen == "first_name":
        return _apply_constraint(fake, fake.first_name(), cons)
    elif gen == "last_name":
        return _apply_constraint(fake, fake.last_name(), cons)
    elif gen == "name":
        return _apply_constraint(fake, fake.name(), cons)
    elif gen == "email":
        return _apply_constraint(fake, fake.email(), cons)
    elif gen == "phone_number":
        return _apply_constraint(fake, fake.phone_number(), cons)
    elif gen == "job":
        return _apply_constraint(fake, fake.job(), cons)
    elif gen == "company":
        return _apply_constraint(fake, fake.company(), cons)
    elif gen in ("company_suffix",):
        return _apply_constraint(fake, fake.company_suffix(), cons)
    elif gen == "catch_phrase":
        return _apply_constraint(fake, fake.catch_phrase(), cons)
    elif gen == "domain_name":
        return _apply_constraint(fake, fake.domain_name(), cons)
    elif gen == "url":
        return _apply_constraint(fake, fake.url(), cons)
    elif gen == "country":
        return _apply_constraint(fake, fake.country(), cons)
    elif gen == "country_code":
        return _apply_constraint(fake, fake.country_code(), cons)
    elif gen == "city":
        return _apply_constraint(fake, fake.city(), cons)
    elif gen == "street_address":
        return _apply_constraint(fake, fake.street_address(), cons)
    elif gen == "zipcode":
        return _apply_constraint(fake, fake.zipcode(), cons)
    elif gen == "text":
        max_len = int(cons.max) if cons and cons.max else 100
        return _apply_constraint(fake, fake.text(max_nb_chars=max_len), cons)
    elif gen == "boolean":
        return _apply_constraint(fake, fake.boolean(), cons)
    elif gen in ("random_int", "pyint"):
        cmin = int(cons.min) if cons and cons.min is not None else 0
        cmax = int(cons.max) if cons and cons.max is not None else 999999
        return _apply_constraint(fake, fake.random_int(min=cmin, max=cmax), cons)
    elif gen == "pydecimal":
        cmin = float(cons.min) if cons and cons.min is not None else 0.0
        cmax = float(cons.max) if cons and cons.max is not None else 999999.99
        digits = cons.right_digits if cons and cons.right_digits is not None else 2
        val = fake.pydecimal(min_value=cmin, max_value=cmax, right_digits=digits)
        return _apply_constraint(fake, float(val), cons)
    elif gen == "uuid4":
        return str(uuid.uuid4())
    elif gen == "uuid_int":
        return uuid.uuid4().int & ((1 << 63) - 1)
    elif gen == "bothify":
        fmt = cons.format if cons and cons.format else "?????#####"
        return _apply_constraint(fake, fake.bothify(text=fmt), cons)
    elif gen == "random_element":
        if cons and cons.values:
            vals = [v.strip() for v in cons.values.split(",")]
            if cons.weights:
                weights = [float(w.strip()) for w in cons.weights.split(",")]
                return _apply_constraint(fake, random.choices(vals, weights=weights, k=1)[0], cons)
            return _apply_constraint(fake, fake.random_element(vals), cons)
        return _apply_constraint(fake, fake.word(), cons)
    elif gen == "currency_code":
        return _apply_constraint(fake, fake.currency_code(), cons)
    elif gen == "swift":
        return _apply_constraint(fake, fake.swift8(), cons)
    elif gen == "iban":
        return _apply_constraint(fake, fake.iban(), cons)
    elif gen == "bban":
        return _apply_constraint(fake, fake.bban(), cons)
    elif gen == "date_between":
        start = cons.start if cons and cons.start else "-5y"
        end = cons.end if cons and cons.end else "today"
        return _apply_constraint(fake, fake.date_between(start_date=start, end_date=end).isoformat(), cons)
    elif gen == "date_of_birth":
        min_age = cons.min_age if cons and cons.min_age is not None else 18
        max_age = cons.max_age if cons and cons.max_age is not None else 99
        dob = fake.date_of_birth(minimum_age=min_age, maximum_age=max_age)
        return _apply_constraint(fake, dob.isoformat(), cons)
    elif gen == "date_time":
        return _apply_constraint(fake, fake.date_time().isoformat(), cons)
    elif gen == "formula":
        return _apply_constraint(fake, field.formula or "", cons)
    elif gen == "shared_key":
        return _apply_constraint(fake, "", cons)
    elif gen == "word":
        return _apply_constraint(fake, fake.word(), cons)
    else:
        return _apply_constraint(fake, fake.word(), cons)


def _generate_dataset(
    fake: Faker,
    definition: DatasetDefinition,
    run_id: int,
    homogeneity: int,
    master_seed: int,
) -> DatasetResult:
    fields = definition.fields
    rows = definition.rows
    dataset_id = str(uuid.uuid4())
    table_name = f"dataset_{dataset_id}"
    validate_table_name(table_name)

    column_names = [validate_column_name(f.name) for f in fields]
    col_types = _infer_duckdb_types(fields)

    db = DuckDBManager.get_instance()

    col_defs = ", ".join(
        f'"{name}" {dtype}' for name, dtype in zip(column_names, col_types, strict=False)
    )
    db.execute(f'CREATE TABLE "{table_name}" ({col_defs})')

    shared_key_pool: list | None = None
    if definition.shared_key:
        sk_table = definition.shared_key.source_dataset
        validate_table_name(f"dataset_{sk_table}")
        sk_field = validate_column_name(definition.shared_key.source_field)
        try:
            result = db.execute(
                f'SELECT "{sk_field}" FROM "dataset_{sk_table}"'
            ).fetchall()
            shared_key_pool = [row[0] for row in result]
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Failed to load shared_key pool")
            shared_key_pool = []

    field_fakers: list[Faker | None] = []
    field_uses_master: list[bool] = []
    for field in fields:
        if field.generator in ("shared_key", "formula", "uuid4", "uuid_int"):
            field_fakers.append(None)
            field_uses_master.append(False)
        else:
            seed_roll = random.randint(1, 100)
            use_master = seed_roll <= homogeneity
            field_uses_master.append(use_master)
            if use_master:
                field_seed = (master_seed + hash(field.name)) % (10**9)
                fk = Faker()
                fk.seed_instance(field_seed)
                field_fakers.append(fk)
            else:
                field_fakers.append(None)

    batch_size = 5000
    columns_formatted = ", ".join(f'"{c}"' for c in column_names)
    placeholders = ", ".join(["?"] * len(column_names))
    insert_sql = f'INSERT INTO "{table_name}" ({columns_formatted}) VALUES ({placeholders})'

    for batch_start in range(0, rows, batch_size):
        batch_end = min(batch_start + batch_size, rows)
        batch_data: list[list] = []

        for row_idx in range(batch_start, batch_end):
            row: list = []
            for fi, field in enumerate(fields):
                if field.null_probability and random.random() < field.null_probability:
                    row.append(None)
                    continue

                if field.condition:
                    if not _check_condition(field.condition, row, fields):
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
                        row.append(field.formula or "")
                    continue

                fk = field_fakers[fi] or fake
                val = _generate_field_value(fk, field, None)
                row.append(val)

            batch_data.append(row)

        db.get_connection().executemany(insert_sql, batch_data)

    result = db.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()
    actual_count = result[0] if result else 0

    columns_json = json.dumps(column_names)
    db.execute(
        """
        INSERT INTO metadata_runs (name, template_name, row_count, homogeneity, seed)
        VALUES (?, ?, ?, ?, ?)
        """,
        [definition.name, definition.template or "", actual_count, homogeneity, master_seed],
    )
    db.execute(
        """
        INSERT INTO metadata_datasets (dataset_id, run_id, name, table_name, columns_json, row_count, homogeneity, seed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [dataset_id, run_id, definition.name, table_name, columns_json, actual_count, homogeneity, master_seed],
    )

    return DatasetResult(
        dataset_id=dataset_id,
        name=definition.name,
        table_name=table_name,
        row_count=actual_count,
        columns=column_names,
    )


def _infer_duckdb_types(fields: list[FieldDefinition]) -> list[str]:
    type_map: list[str] = []
    for f in fields:
        t = f.type.lower()
        if t in ("integer", "int"):
            type_map.append("BIGINT")
        elif t in ("float", "decimal", "number"):
            type_map.append("DOUBLE")
        elif t == "boolean":
            type_map.append("BOOLEAN")
        elif t == "date":
            type_map.append("DATE")
        elif t in ("datetime", "timestamp"):
            type_map.append("TIMESTAMP")
        else:
            type_map.append("VARCHAR")
    return type_map


def generate_datasets(request: GenerateRequest) -> GenerateResponse:
    master_seed = request.seed if request.seed is not None else random.randint(0, 2**31 - 1)
    main_fake = Faker()
    main_fake.seed_instance(master_seed)
    random.seed(master_seed)

    db = DuckDBManager.get_instance()
    result = db.execute("SELECT nextval('seq_run_id')").fetchone()
    run_id = result[0] if result else 1

    dataset_results: list[DatasetResult] = []
    for dataset_def in request.datasets:
        dr = _generate_dataset(
            fake=main_fake,
            definition=dataset_def,
            run_id=run_id,
            homogeneity=request.homogeneity,
            master_seed=master_seed,
        )
        dataset_results.append(dr)

    return GenerateResponse(
        run_id=run_id,
        homogeneity=request.homogeneity,
        seed=master_seed,
        datasets=dataset_results,
    )
