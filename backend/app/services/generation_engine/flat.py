from __future__ import annotations

import logging
import uuid

from faker import Faker

from app.core.database import DuckDBManager
from app.core.validation import validate_column_name, validate_table_name
from app.schemas.generation import DatasetDefinition, DatasetResult
from app.services.generation_engine.fakers import fakers_from_seeds, roll_field_seeds
from app.services.generation_engine.persistence import (
    create_table,
    infer_duckdb_types,
    persist_dataset_metadata,
)
from app.services.generation_engine.row_builder import generate_row
from app.services.generation_engine.sql_generators import build_sql_columns, is_sql_eligible

logger = logging.getLogger(__name__)


def generate_dataset(
    fake: Faker,
    definition: DatasetDefinition,
    run_id: int,
    homogeneity: int,
    master_seed: int,
    overlap_pool: list[dict] | None = None,
    exact_field_names: set[str] | None = None,
) -> DatasetResult:
    fields = definition.fields
    rows = definition.rows
    dataset_id = str(uuid.uuid4())
    table_name = f"dataset_{dataset_id}"
    validate_table_name(table_name)

    column_names = [validate_column_name(f.name) for f in fields]
    col_types = infer_duckdb_types(fields)

    db = DuckDBManager.get_instance()
    create_table(db, table_name, column_names, col_types)

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

    exact_names = exact_field_names or set()
    seeds = roll_field_seeds(fields, homogeneity, master_seed)
    field_fakers = fakers_from_seeds(seeds)

    sql_fields = [f for f in fields if is_sql_eligible(f, exact_names)]
    if sql_fields:
        field_seeds_by_name = {f.name: seeds[i] for i, f in enumerate(fields)}
        sql_columns = build_sql_columns(db, sql_fields, rows, field_seeds_by_name)
    else:
        sql_columns = {}

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
            sql_entry = {name: values[row_idx] for name, values in sql_columns.items()}
            row = generate_row(
                fields,
                field_fakers,
                fake,
                pool_entry={**sql_entry, **pool_entry},
                shared_key_pool=shared_key_pool,
            )
            batch_data.append(row)

        db.executemany(insert_sql, batch_data)

    result = db.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()
    actual_count = result[0] if result else 0

    return persist_dataset_metadata(
        db, definition, dataset_id, table_name, run_id, homogeneity, master_seed, actual_count, column_names
    )
