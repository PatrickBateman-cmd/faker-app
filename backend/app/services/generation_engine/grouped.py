from __future__ import annotations

import random
import uuid

from faker import Faker

from app.core.database import DuckDBManager
from app.core.validation import validate_column_name, validate_table_name
from app.schemas.generation import DatasetDefinition, DatasetResult
from app.services.generation_engine.fakers import build_field_fakers
from app.services.generation_engine.persistence import (
    create_table,
    infer_duckdb_types,
    persist_dataset_metadata,
)
from app.services.generation_engine.row_builder import generate_row


def generate_grouped_dataset(
    fake: Faker,
    definition: DatasetDefinition,
    run_id: int,
    homogeneity: int,
    master_seed: int,
    overlap_pool: list[dict] | None = None,
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
    col_types = infer_duckdb_types(all_fields) + ["VARCHAR"]

    db = DuckDBManager.get_instance()
    create_table(db, table_name, column_names, col_types)

    parent_fakers = build_field_fakers(parent_fields, homogeneity, master_seed, namespace="parent_")
    child_fakers = build_field_fakers(child_fields, homogeneity, master_seed, namespace="child_")

    batch_size = 5000
    columns_formatted = ", ".join(f'"{c}"' for c in column_names)
    placeholders = ", ".join(["?"] * len(column_names))
    insert_sql = f'INSERT INTO "{table_name}" ({columns_formatted}) VALUES ({placeholders})'

    batch_data: list[list] = []
    pool = overlap_pool or []
    row_idx = 0

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
            parent_row = generate_row(parent_fields, parent_fakers, fake)

            child_count = group_sizes[g_idx]
            for _ in range(child_count):
                pool_entry = pool[row_idx] if row_idx < len(pool) else {}
                row_idx += 1
                child_row = generate_row(child_fields, child_fakers, fake, pool_entry=pool_entry)
                batch_data.append(parent_row + child_row + [parent_id])

                if len(batch_data) >= batch_size:
                    db.executemany(insert_sql, batch_data)
                    batch_data = []

    # Flat rows
    for _ in range(flat_rows):
        parent_row = generate_row(parent_fields, parent_fakers, fake)
        pool_entry = pool[row_idx] if row_idx < len(pool) else {}
        row_idx += 1
        child_row = generate_row(child_fields, child_fakers, fake, pool_entry=pool_entry)
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
