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
        self._run_migrations()

    def _init_metadata_tables(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata_schema_version (
                version VARCHAR PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def _run_migrations(self) -> None:
        from app.core.migrations import run_migrations
        run_migrations(conn=self._conn)

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
