from __future__ import annotations

import logging

import duckdb

from app.core.database import DuckDBManager

logger = logging.getLogger(__name__)

MIGRATIONS: list[tuple[str, str]] = [
    (
        "001_initial_schema",
        """
        CREATE SEQUENCE IF NOT EXISTS seq_run_id START 1;
        CREATE TABLE IF NOT EXISTS metadata_templates (
            name VARCHAR PRIMARY KEY,
            category VARCHAR,
            description VARCHAR,
            xml_content VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS metadata_runs (
            run_id INTEGER PRIMARY KEY DEFAULT nextval('seq_run_id'),
            name VARCHAR,
            template_name VARCHAR,
            row_count INTEGER,
            homogeneity INTEGER,
            seed INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS metadata_aggregations (
            id INTEGER PRIMARY KEY DEFAULT nextval('seq_run_id'),
            source_dataset VARCHAR,
            name VARCHAR,
            config_json VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS metadata_datasets (
            dataset_id VARCHAR PRIMARY KEY,
            run_id INTEGER,
            name VARCHAR,
            table_name VARCHAR,
            columns_json VARCHAR,
            row_count INTEGER,
            homogeneity INTEGER,
            seed INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """,
    ),
    (
        "002_iso_cache",
        """
        CREATE TABLE IF NOT EXISTS metadata_iso_cache (
            cache_key VARCHAR PRIMARY KEY,
            data_json VARCHAR,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """,
    ),
    (
        "003_indexes",
        """
        CREATE INDEX IF NOT EXISTS idx_datasets_name ON metadata_datasets(name);
        CREATE INDEX IF NOT EXISTS idx_datasets_created ON metadata_datasets(created_at DESC);
    """,
    ),
    (
        "004_template_runs_relation",
        """
        ALTER TABLE metadata_runs ADD COLUMN IF NOT EXISTS template_name VARCHAR;
    """,
    ),
    (
        "005_dataset_source",
        """
        ALTER TABLE metadata_datasets ADD COLUMN IF NOT EXISTS source VARCHAR;
    """,
    ),
    (
        "006_aggregation_sequence",
        """
        CREATE SEQUENCE IF NOT EXISTS seq_aggregation_id START 1;
    """,
    ),
]


def _get_applied_migrations(conn: duckdb.DuckDBPyConnection | None = None) -> set[str]:
    if conn is None:
        db = DuckDBManager.get_instance()
    else:
        db = conn
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS metadata_schema_version (
            version VARCHAR PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    rows = db.execute("SELECT version FROM metadata_schema_version").fetchall()
    return {r[0] for r in rows}


def run_migrations(conn: duckdb.DuckDBPyConnection | None = None) -> None:
    raw = conn if conn is not None else DuckDBManager.get_instance()._conn
    applied = _get_applied_migrations(conn=conn)
    for name, sql in MIGRATIONS:
        if name not in applied:
            logger.info("Applying migration: %s", name)
            raw.execute("BEGIN")
            try:
                for stmt in (s.strip() for s in sql.strip().split(";") if s.strip()):
                    raw.execute(stmt)
                raw.execute(
                    "INSERT INTO metadata_schema_version (version) VALUES (?)", [name]
                )
                raw.execute("COMMIT")
                logger.info("Migration '%s' applied successfully", name)
            except Exception as e:
                raw.execute("ROLLBACK")
                logger.error("Migration '%s' failed, rolled back: %s", name, e)
                raise
