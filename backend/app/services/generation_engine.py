from __future__ import annotations

import json
import random
import re
import uuid
import logging

from datetime import datetime

from jinja2 import Template as JinjaTemplate

from faker import Faker

logger = logging.getLogger(__name__)

from app.core.database import DuckDBManager
from app.core.validation import validate_column_name, validate_table_name
from app.schemas.generation import (
    ConstraintConfig,
    DatasetDefinition,
    DatasetResult,
    FieldDefinition,
    GenerateRequest,
    GenerateResponse,
    GroupConfig,
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

    try:
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
    except TypeError:
        logger.warning("Type mismatch in condition '%s': %s vs %s", condition, type(field_val).__name__, type(val).__name__)
        return False


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
        logger.warning("Unknown generator '%s' for field '%s', falling back to fake.word()", gen, field.name)
        return _apply_constraint(fake, fake.word(), cons)


def _build_overlap_pool(
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
            entry[field.name] = _generate_field_value(fake, field, None)
        pool.append(entry)
    return pool


def _generate_dataset(
    fake: Faker,
    definition: DatasetDefinition,
    run_id: int,
    homogeneity: int,
    master_seed: int,
    overlap_pool: list[dict] | None = None,
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
            logger.exception("Failed to load shared_key pool")
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

    pool = overlap_pool or []

    for batch_start in range(0, rows, batch_size):
        batch_end = min(batch_start + batch_size, rows)
        batch_data: list[list] = []

        for row_idx in range(batch_start, batch_end):
            pool_entry = pool[row_idx] if row_idx < len(pool) else {}
            row: list = []
            for fi, field in enumerate(fields):
                if field.name in pool_entry:
                    row.append(pool_entry[field.name])
                    continue

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
                        logger.exception("Formula evaluation failed for field '%s'", field.name)
                        row.append(field.formula or "")
                    continue

                fk = field_fakers[fi] or fake
                val = _generate_field_value(fk, field, None)
                row.append(val)

            batch_data.append(row)

        db.executemany(insert_sql, batch_data)

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
            logger.debug("Unrecognized field type '%s' for field '%s', falling back to VARCHAR", f.type, f.name)
            type_map.append("VARCHAR")
    return type_map


def _generate_grouped_dataset(
    fake: Faker,
    definition: DatasetDefinition,
    run_id: int,
    homogeneity: int,
    master_seed: int,
) -> DatasetResult:
    group_cfg = definition.group_config
    assert group_cfg is not None

    total_rows = definition.rows
    num_groups = group_cfg.num_groups
    split_pct = group_cfg.split_pct
    parent_fields = group_cfg.parent_fields
    child_fields = group_cfg.child_fields

    grouped_rows = int(total_rows * split_pct / 100)
    flat_rows = total_rows - grouped_rows

    dataset_id = str(uuid.uuid4())
    table_name = f"dataset_{dataset_id}"
    validate_table_name(table_name)

    all_fields = parent_fields + child_fields
    column_names = [validate_column_name(f.name) for f in all_fields]
    column_names.append("parent_id")
    col_types = _infer_duckdb_types(all_fields) + ["VARCHAR"]

    db = DuckDBManager.get_instance()
    col_defs = ", ".join(
        f'"{name}" {dtype}' for name, dtype in zip(column_names, col_types, strict=False)
    )
    db.execute(f'CREATE TABLE "{table_name}" ({col_defs})')

    parent_fakers: list[Faker | None] = []
    for field in parent_fields:
        if field.generator in ("shared_key", "formula", "uuid4", "uuid_int"):
            parent_fakers.append(None)
        else:
            seed_roll = random.randint(1, 100)
            use_master = seed_roll <= homogeneity
            if use_master:
                field_seed = (master_seed + hash(f"parent_{field.name}")) % (10**9)
                fk = Faker()
                fk.seed_instance(field_seed)
                parent_fakers.append(fk)
            else:
                parent_fakers.append(None)

    child_fakers: list[Faker | None] = []
    for field in child_fields:
        if field.generator in ("shared_key", "formula", "uuid4", "uuid_int"):
            child_fakers.append(None)
        else:
            seed_roll = random.randint(1, 100)
            use_master = seed_roll <= homogeneity
            if use_master:
                field_seed = (master_seed + hash(f"child_{field.name}")) % (10**9)
                fk = Faker()
                fk.seed_instance(field_seed)
                child_fakers.append(fk)
            else:
                child_fakers.append(None)

    def _gen_row(fields: list, fakers: list, row_prefix: list | None = None) -> list:
        row = list(row_prefix) if row_prefix else []
        for fi, field in enumerate(fields):
            if field.null_probability and random.random() < field.null_probability:
                row.append(None)
                continue
            if field.condition:
                if not _check_condition(field.condition, row, fields):
                    row.append(None)
                    continue
            if field.generator == "formula":
                try:
                    t = JinjaTemplate(field.formula or "")
                    already = {f.name: row[idx] for idx, f in enumerate(fields[:fi])}
                    row.append(t.render(**already))
                except Exception:
                    row.append(field.formula or "")
                continue
            fk = fakers[fi] or fake
            row.append(_generate_field_value(fk, field, None))
        return row

    batch_size = 5000
    columns_formatted = ", ".join(f'"{c}"' for c in column_names)
    placeholders = ", ".join(["?"] * len(column_names))
    insert_sql = f'INSERT INTO "{table_name}" ({columns_formatted}) VALUES ({placeholders})'

    batch_data: list[list] = []

    # Distribute grouped_rows randomly across num_groups
    if num_groups > 0 and grouped_rows > 0:
        raw_weights = [random.random() for _ in range(num_groups)]
        total_weight = sum(raw_weights)
        group_sizes = [max(1, int(grouped_rows * w / total_weight)) for w in raw_weights]
        diff = grouped_rows - sum(group_sizes)
        for i in range(abs(diff)):
            group_sizes[i % num_groups] += 1 if diff > 0 else -1
        group_sizes = [max(1, s) for s in group_sizes]

        for g_idx in range(num_groups):
            parent_id = str(uuid.uuid4())
            parent_row = _gen_row(parent_fields, parent_fakers)

            child_count = group_sizes[g_idx]
            for _ in range(child_count):
                child_row = _gen_row(child_fields, child_fakers)
                batch_data.append(parent_row + child_row + [parent_id])

                if len(batch_data) >= batch_size:
                    db.executemany(insert_sql, batch_data)
                    batch_data = []

    # Flat rows
    for _ in range(flat_rows):
        parent_row = _gen_row(parent_fields, parent_fakers)
        child_row = _gen_row(child_fields, child_fakers)
        batch_data.append(parent_row + child_row + [None])

        if len(batch_data) >= batch_size:
            db.executemany(insert_sql, batch_data)
            batch_data = []

    if batch_data:
        db.executemany(insert_sql, batch_data)

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


def generate_datasets(request: GenerateRequest) -> GenerateResponse:
    master_seed = request.seed if request.seed is not None else random.randint(0, 2**31 - 1)
    main_fake = Faker()
    main_fake.seed_instance(master_seed)
    random.seed(master_seed)

    # Validate overlap config before touching DuckDB
    overlap_ratio = request.overlap_ratio
    exact_field_names = set(request.exact_fields)
    if overlap_ratio > 0:
        if not exact_field_names:
            raise ValueError("exact_fields must be specified when overlap_ratio > 0")
        for ds in request.datasets:
            if ds.group_config:
                raise ValueError("overlap is not supported with grouped datasets")
            ds_field_names = {f.name for f in ds.fields}
            for ef in exact_field_names:
                if ef not in ds_field_names:
                    raise ValueError(f"exact field '{ef}' not found in dataset '{ds.name}'")

    db = DuckDBManager.get_instance()
    result = db.execute("SELECT nextval('seq_run_id')").fetchone()
    run_id = result[0] if result else 1

    # Build the global overlap pool once
    overlap_pool: list[dict] = []
    pool_size = 0
    if overlap_ratio > 0 and request.datasets:
        pool_size = int(min(d.rows for d in request.datasets) * overlap_ratio)
        if pool_size > 0:
            first_fields = request.datasets[0].fields
            overlap_pool = _build_overlap_pool(main_fake, first_fields, exact_field_names, pool_size)

    dataset_results: list[DatasetResult] = []
    for dataset_def in request.datasets:
        if dataset_def.group_config:
            dr = _generate_grouped_dataset(
                fake=main_fake,
                definition=dataset_def,
                run_id=run_id,
                homogeneity=request.homogeneity,
                master_seed=master_seed,
            )
        else:
            dr = _generate_dataset(
                fake=main_fake,
                definition=dataset_def,
                run_id=run_id,
                homogeneity=request.homogeneity,
                master_seed=master_seed,
                overlap_pool=overlap_pool,
            )
        dataset_results.append(dr)

    return GenerateResponse(
        run_id=run_id,
        homogeneity=request.homogeneity,
        seed=master_seed,
        datasets=dataset_results,
        overlap_pool_size=pool_size,
        exact_fields=list(exact_field_names),
    )
