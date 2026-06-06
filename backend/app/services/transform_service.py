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


def _render_agg_expr(agg: AggregationDef) -> tuple[str, str]:
    col = validate_column_name(agg.column)
    alias = agg.alias or f"{agg.function}_{col}"
    validate_column_name(alias)
    quoted = f'"{col}"'

    if agg.function == "count_distinct":
        expr = f'COUNT(DISTINCT {quoted}) AS "{alias}"'
    else:
        fn_upper = agg.function.upper()
        expr = f'{fn_upper}({quoted}) AS "{alias}"'
    return expr, alias


def aggregate_dataset(
    source_dataset_id: str,
    request: AggregateRequest,
) -> TransformResponse:
    table_name = _get_table_name(source_dataset_id)
    if not table_name:
        msg = f"Source dataset '{source_dataset_id}' not found"
        raise ValueError(msg)

    db = DuckDBManager.get_instance()

    group_cols_quoted = [f'"{validate_column_name(c)}"' for c in request.group_by]
    agg_parts: list[str] = []
    agg_cols: list[str] = []

    for agg in request.aggregations:
        expr, alias = _render_agg_expr(agg)
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
        INSERT INTO metadata_aggregations (source_dataset, name, config_json)
        VALUES (?, ?, ?)
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
        join_conditions = " AND ".join(
            f'sub2."{validate_column_name(c)}" = sub."{validate_column_name(c)}"'
            for c in request.keys
        )
        sql = f"""
            CREATE TABLE "{result_table}" AS
            SELECT {col_list} FROM (
                SELECT *, {window_sql} FROM "{table_name}"
            ) sub
            WHERE _rn = 1
            AND (SELECT COUNT(*) FROM (
                SELECT 1 FROM "{table_name}" sub2
                WHERE {join_conditions}
            )) = 1
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
        INSERT INTO metadata_aggregations (source_dataset, name, config_json)
        VALUES (?, ?, ?)
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
