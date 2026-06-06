from __future__ import annotations

import os
import re
import tempfile

from app.core.database import DuckDBManager
from app.core.validation import validate_table_name
from app.services.dataset_service import get_dataset


def _sanitize_filename(name: str) -> str:
    return re.sub(r"[^\w.-]", "_", name)


def _get_export_dir() -> str:
    export_dir = os.path.join(tempfile.gettempdir(), "faker_exports")
    os.makedirs(export_dir, exist_ok=True)
    return export_dir


def export_csv(dataset_id: str) -> str:
    meta = get_dataset(dataset_id)
    if not meta:
        raise ValueError(f"Dataset '{dataset_id}' not found")
    table_name = validate_table_name(meta["table_name"])
    safe_name = _sanitize_filename(meta["name"])
    filename = f"{safe_name}_{dataset_id}.csv"
    filepath = os.path.join(_get_export_dir(), filename)
    db = DuckDBManager.get_instance()
    db.execute(
        f"""COPY "{table_name}" TO '{filepath}' (HEADER, DELIMITER ',')"""
    )
    return filepath


def export_parquet(dataset_id: str) -> str:
    meta = get_dataset(dataset_id)
    if not meta:
        raise ValueError(f"Dataset '{dataset_id}' not found")
    table_name = validate_table_name(meta["table_name"])
    safe_name = _sanitize_filename(meta["name"])
    filename = f"{safe_name}_{dataset_id}.parquet"
    filepath = os.path.join(_get_export_dir(), filename)
    db = DuckDBManager.get_instance()
    db.execute(
        f"""COPY "{table_name}" TO '{filepath}' (FORMAT PARQUET)"""
    )
    return filepath


def export_xlsx(dataset_id: str) -> str:
    meta = get_dataset(dataset_id)
    if not meta:
        raise ValueError(f"Dataset '{dataset_id}' not found")
    table_name = validate_table_name(meta["table_name"])
    safe_name = _sanitize_filename(meta["name"])
    filename = f"{safe_name}_{dataset_id}.xlsx"
    filepath = os.path.join(_get_export_dir(), filename)
    db = DuckDBManager.get_instance()
    df = db.execute(f'SELECT * FROM "{table_name}"').fetchdf()
    df.to_excel(filepath, index=False, engine="openpyxl")
    return filepath
