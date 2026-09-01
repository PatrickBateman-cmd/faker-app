from __future__ import annotations

import json
import logging

from app.schemas.generation import DatasetDefinition, DatasetResult, FieldDefinition

logger = logging.getLogger(__name__)


def infer_duckdb_types(fields: list[FieldDefinition]) -> list[str]:
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


def create_table(db, table_name: str, column_names: list[str], col_types: list[str]) -> None:
    col_defs = ", ".join(
        f'"{name}" {dtype}' for name, dtype in zip(column_names, col_types, strict=False)
    )
    db.execute(f'CREATE TABLE "{table_name}" ({col_defs})')


def persist_dataset_metadata(
    db,
    definition: DatasetDefinition,
    dataset_id: str,
    table_name: str,
    run_id: int,
    homogeneity: int,
    master_seed: int,
    actual_count: int,
    column_names: list[str],
) -> DatasetResult:
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
