from __future__ import annotations

import os
import re
import secrets
import tempfile

from app.core.database import DuckDBManager
from app.core.validation import validate_table_name
from app.services.dataset_service import get_dataset

_SAFE_PATH_CHARS = re.compile(r"^[\w.\-/]+$")


def _friendly_name(dataset_name: str) -> str:
    return re.sub(r"[^\w.-]", "_", dataset_name)


def _get_export_dir() -> str:
    export_dir = os.path.join(tempfile.gettempdir(), "faker_exports")
    os.makedirs(export_dir, exist_ok=True)
    return export_dir


def _safe_export_path(ext: str) -> str:
    """Return a UUID-named temp path; never derived from user input."""
    return os.path.join(_get_export_dir(), f"{secrets.token_hex(16)}.{ext}")


def export_csv(dataset_id: str) -> tuple[str, str]:
    meta = get_dataset(dataset_id)
    if not meta:
        raise ValueError(f"Dataset '{dataset_id}' not found")
    table_name = validate_table_name(meta["table_name"])
    filepath = _safe_export_path("csv")
    db = DuckDBManager.get_instance()
    db.execute(f"""COPY "{table_name}" TO '{filepath}' (HEADER, DELIMITER ',')""")
    return filepath, f"{_friendly_name(meta['name'])}_{dataset_id}.csv"


def export_parquet(dataset_id: str) -> tuple[str, str]:
    meta = get_dataset(dataset_id)
    if not meta:
        raise ValueError(f"Dataset '{dataset_id}' not found")
    table_name = validate_table_name(meta["table_name"])
    filepath = _safe_export_path("parquet")
    db = DuckDBManager.get_instance()
    db.execute(f"""COPY "{table_name}" TO '{filepath}' (FORMAT PARQUET)""")
    return filepath, f"{_friendly_name(meta['name'])}_{dataset_id}.parquet"


def export_jsonl(dataset_id: str) -> tuple[str, str]:
    meta = get_dataset(dataset_id)
    if not meta:
        raise ValueError(f"Dataset '{dataset_id}' not found")
    table_name = validate_table_name(meta["table_name"])
    filepath = _safe_export_path("jsonl")
    db = DuckDBManager.get_instance()
    db.execute(f"""COPY "{table_name}" TO '{filepath}' (FORMAT JSON)""")
    return filepath, f"{_friendly_name(meta['name'])}_{dataset_id}.jsonl"


def export_xlsx(dataset_id: str) -> tuple[str, str]:
    meta = get_dataset(dataset_id)
    if not meta:
        raise ValueError(f"Dataset '{dataset_id}' not found")
    table_name = validate_table_name(meta["table_name"])
    filepath = _safe_export_path("xlsx")
    db = DuckDBManager.get_instance()
    df = db.execute(f'SELECT * FROM "{table_name}"').fetchdf()
    df.to_excel(filepath, index=False, engine="openpyxl")
    return filepath, f"{_friendly_name(meta['name'])}_{dataset_id}.xlsx"
