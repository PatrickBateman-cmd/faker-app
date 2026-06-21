from __future__ import annotations

import json

from app.core.database import DuckDBManager
from app.core.validation import validate_table_name


def list_datasets() -> list[dict]:
    db = DuckDBManager.get_instance()
    rows = db.execute(
        """
        SELECT dataset_id, name, table_name, row_count, columns_json, homogeneity, seed, created_at
        FROM metadata_datasets
        ORDER BY created_at DESC
        """
    ).fetchall()
    return [
        {
            "dataset_id": r[0],
            "name": r[1],
            "table_name": r[2],
            "row_count": r[3],
            "columns": json.loads(r[4]) if r[4] else [],
            "homogeneity": r[5],
            "seed": r[6],
            "created_at": str(r[7]) if r[7] else None,
        }
        for r in rows
    ]


def get_dataset(dataset_id: str) -> dict | None:
    db = DuckDBManager.get_instance()
    row = db.execute(
        """
        SELECT dataset_id, name, table_name, row_count, columns_json, homogeneity, seed, created_at
        FROM metadata_datasets
        WHERE dataset_id = ?
        """,
        [dataset_id],
    ).fetchone()
    if not row:
        return None
    return {
        "dataset_id": row[0],
        "name": row[1],
        "table_name": row[2],
        "row_count": row[3],
        "columns": json.loads(row[4]) if row[4] else [],
        "homogeneity": row[5],
        "seed": row[6],
        "created_at": str(row[7]) if row[7] else None,
    }


def get_dataset_rows(
    dataset_id: str,
    page: int = 1,
    per_page: int = 100,
) -> dict:
    meta = get_dataset(dataset_id)
    if not meta:
        return {"rows": [], "total": 0, "page": page, "per_page": per_page, "meta": None}

    table_name = validate_table_name(meta["table_name"])
    offset = (page - 1) * per_page
    db = DuckDBManager.get_instance()

    count_row = db.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()
    total = count_row[0] if count_row else 0

    rows = db.execute(
        f'SELECT * FROM "{table_name}" LIMIT ? OFFSET ?',
        [per_page, offset],
    ).fetchall()

    columns = [desc[0] for desc in db.execute(f'SELECT * FROM "{table_name}" LIMIT 0').description]

    data = [dict(zip(columns, row, strict=True)) for row in rows]

    return {
        "rows": data,
        "total": total,
        "page": page,
        "per_page": per_page,
        "meta": meta,
    }


def rename_dataset(dataset_id: str, new_name: str) -> bool:
    meta = get_dataset(dataset_id)
    if not meta:
        return False
    db = DuckDBManager.get_instance()
    db.execute("UPDATE metadata_datasets SET name = ? WHERE dataset_id = ?", [new_name, dataset_id])
    return True


def delete_dataset(dataset_id: str) -> bool:
    meta = get_dataset(dataset_id)
    if not meta:
        return False

    db = DuckDBManager.get_instance()
    table_name = validate_table_name(meta["table_name"])
    db.execute(f'DROP TABLE IF EXISTS "{table_name}"')
    db.execute("DELETE FROM metadata_aggregations WHERE source_dataset = ?", [dataset_id])
    db.execute("DELETE FROM metadata_datasets WHERE dataset_id = ?", [dataset_id])
    return True


def get_dataset_columns(dataset_id: str) -> list[dict]:
    meta = get_dataset(dataset_id)
    if not meta:
        return []

    db = DuckDBManager.get_instance()
    table_name = validate_table_name(meta["table_name"])
    result = db.execute(f'DESCRIBE "{table_name}"').fetchall()

    return [
        {"name": r[0], "type": r[1], "dataset_id": dataset_id}
        for r in result
    ]
