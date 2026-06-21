from __future__ import annotations

import json
import uuid

from app.core.database import DuckDBManager
from app.core.validation import validate_column_name, validate_table_name
from app.schemas.aggregation import (
    AggregateRequest,
    AggregationDef,
    DedupRequest,
    TransformResponse,
)
from app.services.dataset_service import get_dataset


def _get_table_name(source_dataset_id: str) -> str | None:
    meta = get_dataset(source_dataset_id)
    if not meta:
        return None
    return validate_table_name(meta["table_name"])


_NUMERIC_AGG_FUNCTIONS = {"AVG", "SUM", "MIN", "MAX"}


def _render_agg_expr(agg: AggregationDef, col_types: dict[str, str] | None = None) -> tuple[str, str]:
    col = validate_column_name(agg.column)
    alias = agg.alias or f"{agg.function}_{col}"
    validate_column_name(alias)
    quoted = f'"{col}"'

    if agg.function == "count_distinct":
        expr = f'COUNT(DISTINCT {quoted}) AS "{alias}"'
    else:
        fn_upper = agg.function.upper()
        raw_type = col_types.get(col, "").upper() if col_types else ""
        if col_types and fn_upper in _NUMERIC_AGG_FUNCTIONS and raw_type.startswith("VARCHAR"):
            quoted = f'CAST("{col}" AS DOUBLE)'
        expr = f'{fn_upper}({quoted}) AS "{alias}"'
    return expr, alias


def _get_column_types(table_name: str) -> dict[str, str]:
    db = DuckDBManager.get_instance()
    rows = db.execute(f'DESCRIBE "{table_name}"').fetchall()
    return {r[0]: r[1] for r in rows}


def aggregate_dataset(
    source_dataset_id: str,
    request: AggregateRequest,
) -> TransformResponse:
    table_name = _get_table_name(source_dataset_id)
    if not table_name:
        msg = f"Source dataset '{source_dataset_id}' not found"
        raise ValueError(msg)

    db = DuckDBManager.get_instance()
    col_types = _get_column_types(table_name)

    group_cols_quoted = [f'"{validate_column_name(c)}"' for c in request.group_by]
    agg_parts: list[str] = []
    agg_cols: list[str] = []

    for agg in request.aggregations:
        expr, alias = _render_agg_expr(agg, col_types)
        agg_parts.append(expr)
        agg_cols.append(alias)

    all_cols = group_cols_quoted + agg_parts
    select_clause = ", ".join(all_cols)
    group_clause = ", ".join(group_cols_quoted)

    sql = f'SELECT {select_clause} FROM "{table_name}" GROUP BY {group_clause}'

    result_id = str(uuid.uuid4())
    result_table = f"dataset_{result_id}"
    db.execute(f'CREATE TABLE "{result_table}" AS {sql}')

    count_row = db.execute(f'SELECT COUNT(*) FROM "{result_table}"').fetchone()
    actual_count = count_row[0] if count_row else 0

    columns = request.group_by + agg_cols
    _register_dataset(result_id, request.name, result_table, columns, actual_count)

    db.execute(
        """
        INSERT INTO metadata_aggregations (id, source_dataset, name, config_json)
        VALUES (nextval('seq_aggregation_id'), ?, ?, ?)
        """,
        [source_dataset_id, request.name, json.dumps(request.model_dump())],
    )

    return TransformResponse(
        dataset_id=result_id,
        name=request.name,
        table_name=result_table,
        row_count=actual_count,
        columns=columns,
        source_dataset=source_dataset_id,
        transform_type="aggregate",
    )


def dedup_dataset(
    source_dataset_id: str,
    request: DedupRequest,
) -> TransformResponse:
    table_name = _get_table_name(source_dataset_id)
    if not table_name:
        msg = f"Source dataset '{source_dataset_id}' not found"
        raise ValueError(msg)

    db = DuckDBManager.get_instance()

    key_cols_quoted = [f'"{validate_column_name(c)}"' for c in request.keys]
    partition_by = ", ".join(key_cols_quoted)

    all_cols = _get_table_columns(table_name)
    col_list = ", ".join(f'"{c}"' for c in all_cols)

    order_col = request.order_by.column if request.order_by else all_cols[0]
    validate_column_name(order_col)
    order_dir = request.order_by.direction.upper() if request.order_by else "DESC"

    if request.strategy == "keep_last":
        order_dir = "ASC" if order_dir == "DESC" else "DESC"

    window_sql = f'ROW_NUMBER() OVER (PARTITION BY {partition_by} ORDER BY "{order_col}" {order_dir}) AS _rn'

    all_cols = _get_table_columns(table_name)
    col_list = ", ".join(f'"{c}"' for c in all_cols)

    result_id = str(uuid.uuid4())
    result_table = f"dataset_{result_id}"

    if request.strategy == "keep_none":
        key_quoted_list = [f'"{validate_column_name(c)}"' for c in request.keys]
        key_tuple = f"({', '.join(key_quoted_list)})"
        group_by_clause = ", ".join(key_quoted_list)
        sql = f"""
            CREATE TABLE "{result_table}" AS
            SELECT {col_list} FROM "{table_name}"
            WHERE {key_tuple} IN (
                SELECT {key_tuple} FROM "{table_name}"
                GROUP BY {group_by_clause}
                HAVING COUNT(*) = 1
            )
        """
    else:
        sql = f"""
            CREATE TABLE "{result_table}" AS
            SELECT {col_list} FROM (
                SELECT *, {window_sql} FROM "{table_name}"
            ) sub
            WHERE _rn = 1
        """

    db.execute(sql)

    count_row = db.execute(f'SELECT COUNT(*) FROM "{result_table}"').fetchone()
    actual_count = count_row[0] if count_row else 0

    _register_dataset(result_id, request.name, result_table, all_cols, actual_count)

    db.execute(
        """
        INSERT INTO metadata_aggregations (id, source_dataset, name, config_json)
        VALUES (nextval('seq_aggregation_id'), ?, ?, ?)
        """,
        [source_dataset_id, request.name, json.dumps(request.model_dump())],
    )

    return TransformResponse(
        dataset_id=result_id,
        name=request.name,
        table_name=result_table,
        row_count=actual_count,
        columns=all_cols,
        source_dataset=source_dataset_id,
        transform_type="dedup",
    )


def _register_dataset(
    dataset_id: str,
    name: str,
    table_name: str,
    columns: list[str],
    row_count: int,
) -> None:
    db = DuckDBManager.get_instance()
    db.execute(
        """
        INSERT INTO metadata_datasets (dataset_id, run_id, name, table_name, columns_json, row_count, homogeneity, seed)
        VALUES (?, NULL, ?, ?, ?, ?, NULL, NULL)
        """,
        [dataset_id, name, table_name, json.dumps(columns), row_count],
    )


def _get_table_columns(table_name: str) -> list[str]:
    db = DuckDBManager.get_instance()
    result = db.execute(f'DESCRIBE "{table_name}"').fetchall()
    return [r[0] for r in result]
