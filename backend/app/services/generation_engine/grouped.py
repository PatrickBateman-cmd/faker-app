from __future__ import annotations

import random
import uuid

from faker import Faker

from app.core.database import DuckDBManager
from app.core.validation import validate_column_name, validate_table_name
from app.schemas.generation import DatasetDefinition, DatasetResult, FieldBreakConfig
from app.services.generation_engine.breaks import BreakRecord, apply_field_breaks
from app.services.generation_engine.fakers import fakers_from_seeds, roll_field_seeds
from app.services.generation_engine.persistence import (
    create_table,
    infer_duckdb_types,
    persist_dataset_metadata,
)
from app.services.generation_engine.row_builder import generate_row
from app.services.generation_engine.sql_generators import build_sql_columns, is_sql_eligible


def generate_grouped_dataset(
    fake: Faker,
    definition: DatasetDefinition,
    run_id: int,
    homogeneity: int,
    master_seed: int,
    overlap_pool: list[dict] | None = None,
    exact_field_names: set[str] | None = None,
    join_key_field: str | None = None,
    field_breaks: dict[str, FieldBreakConfig] | None = None,
    ground_truth: list[BreakRecord] | None = None,
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
    grouped_enabled = num_groups > 0 and grouped_rows > 0

    dataset_id = str(uuid.uuid4())
    table_name = f"dataset_{dataset_id}"
    validate_table_name(table_name)

    all_fields = parent_fields + child_fields
    column_names = [validate_column_name(f.name) for f in all_fields]
    column_names.append("parent_id")
    col_types = infer_duckdb_types(all_fields) + ["VARCHAR"]

    db = DuckDBManager.get_instance()
    create_table(db, table_name, column_names, col_types)

    exact_names = exact_field_names or set()

    parent_seeds = roll_field_seeds(parent_fields, homogeneity, master_seed, namespace="parent_")
    parent_fakers = fakers_from_seeds(parent_seeds)
    child_seeds = roll_field_seeds(child_fields, homogeneity, master_seed, namespace="child_")
    child_fakers = fakers_from_seeds(child_seeds)

    child_field_names = [f.name for f in child_fields]
    join_key_col_idx = (
        child_field_names.index(join_key_field)
        if join_key_field and join_key_field in child_field_names
        else None
    )

    # Distribute grouped_rows randomly across num_groups.
    # This must be computed before sql_child_columns is sized, since over-generation
    # from the diff-correction/clamping logic below can make sum(group_sizes) > grouped_rows.
    if grouped_enabled:
        raw_weights = [random.random() for _ in range(num_groups)]
        total_weight = sum(raw_weights)
        group_sizes = [max(1, int(grouped_rows * w / total_weight)) for w in raw_weights]
        diff = grouped_rows - sum(group_sizes)
        for i in range(abs(diff)):
            group_sizes[i % num_groups] += 1 if diff > 0 else -1
        group_sizes = [max(1, s) for s in group_sizes]
    else:
        group_sizes = []

    parent_call_count = (num_groups if grouped_enabled else 0) + flat_rows
    sql_parent_fields = [f for f in parent_fields if is_sql_eligible(f, exact_names)]
    if sql_parent_fields:
        parent_seeds_by_name = {f.name: parent_seeds[i] for i, f in enumerate(parent_fields)}
        sql_parent_columns = build_sql_columns(db, sql_parent_fields, parent_call_count, parent_seeds_by_name)
    else:
        sql_parent_columns = {}

    child_call_count = sum(group_sizes) + flat_rows
    sql_child_fields = [f for f in child_fields if is_sql_eligible(f, exact_names)]
    if sql_child_fields:
        child_seeds_by_name = {f.name: child_seeds[i] for i, f in enumerate(child_fields)}
        sql_child_columns = build_sql_columns(db, sql_child_fields, child_call_count, child_seeds_by_name)
    else:
        sql_child_columns = {}

    batch_size = 5000
    columns_formatted = ", ".join(f'"{c}"' for c in column_names)
    placeholders = ", ".join(["?"] * len(column_names))
    insert_sql = f'INSERT INTO "{table_name}" ({columns_formatted}) VALUES ({placeholders})'

    batch_data: list[list] = []
    pool = overlap_pool or []
    row_idx = 0
    parent_call_idx = 0

    def _next_parent_row() -> list:
        nonlocal parent_call_idx
        sql_entry = {name: values[parent_call_idx] for name, values in sql_parent_columns.items()}
        parent_row = generate_row(parent_fields, parent_fakers, fake, pool_entry=sql_entry)
        parent_call_idx += 1
        return parent_row

    if grouped_enabled:
        for g_idx in range(num_groups):
            parent_id = str(uuid.uuid4())
            parent_row = _next_parent_row()

            child_count = group_sizes[g_idx]
            for _ in range(child_count):
                pool_entry = pool[row_idx] if row_idx < len(pool) else {}
                sql_entry = {name: values[row_idx] for name, values in sql_child_columns.items()}
                row_idx += 1
                child_row = generate_row(
                    child_fields, child_fakers, fake, pool_entry={**sql_entry, **pool_entry}
                )
                if field_breaks and join_key_col_idx is not None:
                    row_breaks = apply_field_breaks(
                        child_row, child_fields, field_breaks, child_row[join_key_col_idx], dataset_id, fake
                    )
                    if ground_truth is not None:
                        ground_truth.extend(row_breaks)
                batch_data.append(parent_row + child_row + [parent_id])

                if len(batch_data) >= batch_size:
                    db.executemany(insert_sql, batch_data)
                    batch_data = []

    # Flat rows
    for _ in range(flat_rows):
        parent_row = _next_parent_row()
        pool_entry = pool[row_idx] if row_idx < len(pool) else {}
        sql_entry = {name: values[row_idx] for name, values in sql_child_columns.items()}
        row_idx += 1
        child_row = generate_row(
            child_fields, child_fakers, fake, pool_entry={**sql_entry, **pool_entry}
        )
        if field_breaks and join_key_col_idx is not None:
            row_breaks = apply_field_breaks(
                child_row, child_fields, field_breaks, child_row[join_key_col_idx], dataset_id, fake
            )
            if ground_truth is not None:
                ground_truth.extend(row_breaks)
        batch_data.append(parent_row + child_row + [None])

        if len(batch_data) >= batch_size:
            db.executemany(insert_sql, batch_data)
            batch_data = []

    if batch_data:
        db.executemany(insert_sql, batch_data)

    result = db.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()
    actual_count = result[0] if result else 0

    return persist_dataset_metadata(
        db, definition, dataset_id, table_name, run_id, homogeneity, master_seed, actual_count, column_names
    )
