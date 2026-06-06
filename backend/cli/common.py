import json as _json
import os
import sys

import typer
from rich.console import Console

from app.config import settings
from app.core.database import DuckDBManager

console = Console()
DB_PATH = typer.Option(None, "--db", "-d", help="DuckDB path override (default from .env)")


class CliState:
    def __init__(self, db_path: str | None = None):
        self._db_initialized = False
        self._db_path = db_path or settings.duckdb_path

    def ensure_db(self, db: str | None = None) -> DuckDBManager:
        path = self._resolve_path(db)
        try:
            mgr = DuckDBManager.get_instance()
        except RuntimeError:
            mgr = DuckDBManager.initialize(db_path=path)
            self._db_initialized = True
            self._db_path = path
            return mgr
        if not self._db_initialized:
            self._db_initialized = True
            self._db_path = path
        return mgr

    def _resolve_path(self, db: str | None) -> str:
        if db:
            return os.path.abspath(db)
        return os.path.abspath(self._db_path)

    @property
    def db_path(self) -> str:
        return self._db_path

    @db_path.setter
    def db_path(self, value: str) -> None:
        self._db_path = value


_state: CliState | None = None


def get_state() -> CliState:
    global _state
    if _state is None:
        _state = CliState()
    return _state


def print_table(title: str, columns: list[str], rows: list[list]) -> None:
    from rich.table import Table

    table = Table(title=title, title_style="bold cyan")
    for col in columns:
        table.add_column(col, style="cyan" if col == columns[0] else None)

    for row in rows:
        table.add_row(*[str(c) if c is not None else "" for c in row])

    console.print(table)


def print_json(data: object) -> None:
    console.print(_json.dumps(data, indent=2, default=str))


def output_result(
    title: str,
    columns: list[str],
    rows: list[list],
    fmt: str,
    json_data: object = None,
) -> None:
    if fmt == "json":
        print_json(json_data if json_data is not None else [dict(zip(columns, r)) for r in rows])
    else:
        print_table(title, columns, rows)
