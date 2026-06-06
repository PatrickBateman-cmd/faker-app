from __future__ import annotations

import os
import threading
from pathlib import Path

import duckdb


class DuckDBManager:
    _instance: DuckDBManager | None = None
    _lock = threading.Lock()

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        os.makedirs(db_path, exist_ok=True)
        db_file = Path(db_path) / "default_user.duckdb"
        self._conn = duckdb.connect(str(db_file))
        self._init_metadata_tables()

    def _init_metadata_tables(self) -> None:
        self._conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS seq_run_id START 1
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata_templates (
                name VARCHAR PRIMARY KEY,
                category VARCHAR,
                description VARCHAR,
                xml_content VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata_runs (
                run_id INTEGER PRIMARY KEY DEFAULT nextval('seq_run_id'),
                name VARCHAR,
                template_name VARCHAR,
                row_count INTEGER,
                homogeneity INTEGER,
                seed INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata_aggregations (
                id INTEGER PRIMARY KEY DEFAULT nextval('seq_run_id'),
                source_dataset VARCHAR,
                name VARCHAR,
                config_json VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._conn.execute("""
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
            )
        """)

    def execute(self, sql: str, params: list | None = None) -> duckdb.DuckDBPyConnection:
        with self._lock:
            if params:
                return self._conn.execute(sql, params)
            return self._conn.execute(sql)

    def get_connection(self) -> duckdb.DuckDBPyConnection:
        return self._conn

    def close(self) -> None:
        self._conn.close()

    @classmethod
    def initialize(cls, db_path: str = "./duckdb") -> DuckDBManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(db_path)
        return cls._instance

    @classmethod
    def get_instance(cls) -> DuckDBManager:
        if cls._instance is None:
            msg = "DuckDBManager not initialized. Call initialize() first."
            raise RuntimeError(msg)
        return cls._instance

    @classmethod
    def close_instance(cls) -> None:
        with cls._lock:
            if cls._instance is not None:
                cls._instance.close()
                cls._instance = None
