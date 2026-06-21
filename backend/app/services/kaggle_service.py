from __future__ import annotations

import json
import os
import tempfile
import uuid
import zipfile
from logging import getLogger
from pathlib import Path

from app.config import settings
from app.core.database import DuckDBManager
from app.core.validation import validate_table_name

logger = getLogger(__name__)


def _setup_env() -> bool:
    """Push credentials into env vars so the kaggle package picks them up."""
    if settings.kaggle_api_token:
        os.environ.setdefault("KAGGLE_API_TOKEN", settings.kaggle_api_token)
        return True
    if settings.kaggle_username and settings.kaggle_key:
        os.environ.setdefault("KAGGLE_USERNAME", settings.kaggle_username)
        os.environ.setdefault("KAGGLE_KEY", settings.kaggle_key)
        return True
    return (Path.home() / ".kaggle" / "kaggle.json").exists() or \
           (Path.home() / ".kaggle" / "access_token").exists()


def credentials_configured() -> bool:
    return _setup_env()


def _get_api():
    if not _setup_env():
        raise ValueError(
            "Kaggle credentials not configured. Set KAGGLE_API_TOKEN as an environment "
            "variable, or create ~/.kaggle/kaggle.json"
        )
    from kaggle.api.kaggle_api_extended import KaggleApi
    api = KaggleApi()
    api.authenticate()
    return api


def search_datasets(q: str, page: int = 1, per_page: int = 20) -> dict:
    api = _get_api()
    results = api.dataset_list(search=q, page=page, file_type="csv", max_size=500)
    datasets = []
    for d in results:
        files = getattr(d, "files", None) or []
        datasets.append({
            "ref": str(d.ref) if d.ref else "",
            "title": str(d.title) if d.title else "",
            "size": int(d.total_bytes) if d.total_bytes else 0,
            "last_updated": str(d.last_updated) if d.last_updated else "",
            "download_count": int(d.download_count) if d.download_count else 0,
            "vote_count": int(d.vote_count) if d.vote_count else 0,
            "usability_rating": float(d.usability_rating) if d.usability_rating else 0.0,
            "file_count": len(files),
        })
    return {"datasets": datasets[:per_page], "total": len(results)}


def list_files(owner: str, slug: str) -> list[dict]:
    api = _get_api()
    result = api.dataset_list_files(f"{owner}/{slug}")
    files = []
    for f in getattr(result, "dataset_files", []):
        name = str(f.name) if f.name else ""
        if name.lower().endswith(".csv"):
            files.append({
                "name": name,
                "size": int(f.total_bytes) if f.total_bytes else 0,
                "creation_date": str(f.creation_date) if f.creation_date else "",
            })
    return files


def import_file(
    owner: str,
    slug: str,
    file_name: str,
    dataset_name: str | None = None,
    max_rows: int | None = None,
) -> dict:
    api = _get_api()
    dataset = f"{owner}/{slug}"
    logger.info("Downloading %s/%s from Kaggle", dataset, file_name)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        csv_path: str | None = None

        # Try single-file download first
        try:
            api.dataset_download_file(dataset, file_name, path=tmpdir, force=True, quiet=True)
            # The package may write file.csv.zip or file.csv directly
            zip_candidate = tmppath / f"{file_name}.zip"
            direct_candidate = tmppath / file_name
            if zip_candidate.exists():
                with zipfile.ZipFile(zip_candidate) as zf:
                    csv_members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
                    if not csv_members:
                        raise ValueError("Zip contains no CSV files")
                    target = file_name if file_name in csv_members else csv_members[0]
                    extract_path = tmppath / "extracted"
                    extract_path.mkdir()
                    zf.extract(target, extract_path)
                    csv_path = str(extract_path / target)
            elif direct_candidate.exists():
                csv_path = str(direct_candidate)
        except Exception as e:
            logger.info("Single-file download failed (%s), falling back to full dataset", e)

        # Fallback: download full dataset and find the CSV
        if csv_path is None:
            api.dataset_download_files(dataset, path=tmpdir, force=True, quiet=True, unzip=True)
            all_csvs = list(tmppath.rglob("*.csv"))
            if not all_csvs:
                raise ValueError(f"No CSV files found after downloading dataset {dataset}")
            # Prefer the requested file name, otherwise pick the first
            csv_path = str(
                next((f for f in all_csvs if f.name == file_name), all_csvs[0])
            )

        return _ingest_csv(
            csv_path=csv_path,
            owner=owner,
            slug=slug,
            file_name=file_name,
            dataset_name=dataset_name,
            max_rows=max_rows,
        )


def _ingest_csv(
    csv_path: str,
    owner: str,
    slug: str,
    file_name: str,
    dataset_name: str | None,
    max_rows: int | None,
) -> dict:
    dataset_id = str(uuid.uuid4())
    table_name = f"dataset_{dataset_id}"
    validate_table_name(table_name)

    effective_max = max_rows or settings.max_rows_per_dataset
    if not isinstance(effective_max, int) or effective_max <= 0:
        raise ValueError(f"Invalid max_rows: {effective_max}")
    db = DuckDBManager.get_instance()

    db.execute(
        f"""
        CREATE TABLE "{table_name}" AS
        SELECT * FROM read_csv_auto(?, normalize_names=true, ignore_errors=true)
        LIMIT ?
        """,
        [csv_path, effective_max],
    )

    desc = db.execute(f'DESCRIBE "{table_name}"').fetchall()
    columns = [r[0] for r in desc]

    count_row = db.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()
    row_count = count_row[0] if count_row else 0

    columns_json = json.dumps(columns)
    name = dataset_name or f"{slug}/{file_name}"
    source = f"kaggle:{owner}/{slug}/{file_name}"

    db.execute(
        """
        INSERT INTO metadata_datasets
            (dataset_id, run_id, name, table_name, columns_json, row_count, homogeneity, seed, source)
        VALUES (?, NULL, ?, ?, ?, ?, NULL, NULL, ?)
        """,
        [dataset_id, name, table_name, columns_json, row_count, source],
    )

    logger.info("Imported Kaggle dataset '%s': %d rows, %d cols", name, row_count, len(columns))
    return {
        "dataset_id": dataset_id,
        "name": name,
        "table_name": table_name,
        "row_count": row_count,
        "columns": columns,
    }
