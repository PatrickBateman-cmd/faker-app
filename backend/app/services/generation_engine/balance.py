from __future__ import annotations

import json
import logging
import uuid

from app.core.database import DuckDBManager
from app.core.validation import validate_column_name, validate_table_name
from app.schemas.generation import BalanceConfig, DatasetResult
from app.services.generation_engine.persistence import create_table

logger = logging.getLogger(__name__)

_DATE_TYPES = {"DATE", "TIMESTAMP"}
_NUMERIC_TYPES = {"BIGINT", "INTEGER", "DOUBLE", "DECIMAL", "FLOAT", "REAL", "TINYINT", "SMALLINT", "HUGEINT", "UBIGINT", "UINTEGER"}

BALANCE_COLUMNS = [
    "partition_date",
    "opening_balance",
    "sum_positives",
    "sum_negatives",
    "closing_balance",
    "record_count",
]


def _sign_expr(config: BalanceConfig) -> str:
    amount = validate_column_name(config.amount_field)
    if not config.sign_field:
        return f'"{amount}"'
    sign_field = validate_column_name(config.sign_field)
    if config.positive_values:
        literals = ", ".join(
            "'" + v.replace("'", "''") + "'" for v in config.positive_values
        )
        cond = f'"{sign_field}" IN ({literals})'
    else:
        cond = "1 = 0"
    return f'CASE WHEN {cond} THEN "{amount}" ELSE -("{amount}") END'


def _column_types(table_name: str) -> dict[str, str]:
    db = DuckDBManager.get_instance()
    rows = db.execute(f'DESCRIBE "{table_name}"').fetchall()
    return {r[0]: r[1] for r in rows}


def _validate_columns(config: BalanceConfig, col_types: dict[str, str]) -> None:
    cols = set(col_types)
    for c in [config.date_field, config.amount_field, *config.group_by, *([config.sign_field] if config.sign_field else [])]:
        if c not in cols:
            raise ValueError(
                f"balance '{config.name}': column '{c}' not found in source dataset '{config.source_dataset}'"
            )
    if col_types.get(config.date_field, "").upper() not in _DATE_TYPES:
        raise ValueError(
            f"balance '{config.name}': date_field '{config.date_field}' must be DATE or TIMESTAMP, "
            f"got '{col_types.get(config.date_field)}'"
        )
    if col_types.get(config.amount_field, "").upper() not in _NUMERIC_TYPES:
        raise ValueError(
            f"balance '{config.name}': amount_field '{config.amount_field}' must be numeric, "
            f"got '{col_types.get(config.amount_field)}'"
        )


def build_balance_sql(source_table: str, config: BalanceConfig, col_types: dict[str, str]) -> str:
    date_col = validate_column_name(config.date_field)
    amt = validate_column_name(config.amount_field)
    group_cols = [validate_column_name(c) for c in config.group_by]
    if col_types.get(config.date_field, "").upper() == "TIMESTAMP":
        date_expr = f'CAST("{date_col}" AS DATE)'
    else:
        date_expr = f'"{date_col}"'

    group_select = ", ".join(f'"{c}"' for c in group_cols)
    group_clause_list = [f'"{c}"' for c in group_cols]

    if config.group_by:
        select_group = f", {group_select}"
        group_clause = ", ".join([date_expr] + group_clause_list)
    else:
        select_group = ""
        group_clause = date_expr

    sgn = _sign_expr(config)

    return f"""
        SELECT
            {date_expr} AS _pdate{select_group},
            SUM(CASE WHEN sgn > 0 THEN sgn ELSE 0 END) AS sum_pos,
            SUM(CASE WHEN sgn < 0 THEN sgn ELSE 0 END) AS sum_neg,
            COUNT(*) AS record_count
        FROM (
            SELECT *, {sgn} AS sgn
            FROM "{source_table}"
        ) _sub
        GROUP BY {group_clause}
        ORDER BY _pdate, {group_select}
    """


def _continuity_rows(
    agg_rows: list[list],
    num_group_cols: int,
    opening_balance: float | None,
) -> list[list]:
    opening_default = float(opening_balance) if opening_balance is not None else 0.0
    last_closing: dict[tuple, float] = {}
    out: list[list] = []
    for row in agg_rows:
        pdate = row[0]
        group_vals = row[1 : 1 + num_group_cols]
        sum_pos = float(row[1 + num_group_cols] or 0.0)
        sum_neg = float(row[2 + num_group_cols] or 0.0)
        record_count = int(row[3 + num_group_cols])
        key = tuple(group_vals)
        opening = last_closing.get(key, opening_default)
        closing = opening + sum_pos + sum_neg
        last_closing[key] = closing
        out.append([
            pdate,
            *group_vals,
            round(opening, 2),
            round(sum_pos, 2),
            round(sum_neg, 2),
            round(closing, 2),
            record_count,
        ])
    return out


def generate_balance_dataset(
    source_table: str,
    config: BalanceConfig,
    run_id: int,
    homogeneity: int,
    master_seed: int,
) -> DatasetResult:
    db = DuckDBManager.get_instance()
    validate_table_name(source_table)
    col_types = _column_types(source_table)
    _validate_columns(config, col_types)

    sql = build_balance_sql(source_table, config, col_types)
    agg_rows = db.execute(sql).fetchall()

    group_types = [col_types.get(c, "VARCHAR") for c in config.group_by]
    num_group_cols = len(config.group_by)
    rows = _continuity_rows(agg_rows, num_group_cols, config.opening_balance)

    dataset_id = str(uuid.uuid4())
    table_name = f"dataset_{dataset_id}"
    validate_table_name(table_name)

    column_names = (
        ["partition_date", *config.group_by]
        + BALANCE_COLUMNS[1:]
    )
    col_types_out = (
        ["DATE", *group_types]
        + ["DOUBLE", "DOUBLE", "DOUBLE", "DOUBLE", "BIGINT"]
    )
    create_table(db, table_name, column_names, col_types_out)

    columns_formatted = ", ".join(f'"{c}"' for c in column_names)
    placeholders = ", ".join(["?"] * len(column_names))
    insert_sql = f'INSERT INTO "{table_name}" ({columns_formatted}) VALUES ({placeholders})'
    if rows:
        db.executemany(insert_sql, rows)

    count = len(rows)
    db.execute(
        """
        INSERT INTO metadata_datasets (dataset_id, run_id, name, table_name, columns_json, row_count, homogeneity, seed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            dataset_id,
            run_id,
            config.name,
            table_name,
            json.dumps(column_names),
            count,
            homogeneity,
            master_seed,
        ],
    )
    db.execute(
        """
        INSERT INTO metadata_balance_sets (id, run_id, dataset_id, source_dataset, name, config_json)
        VALUES (nextval('seq_balance_id'), ?, ?, ?, ?, ?)
        """,
        [run_id, dataset_id, config.source_dataset, config.name, json.dumps(config.model_dump())],
    )

    return DatasetResult(
        dataset_id=dataset_id,
        name=config.name,
        table_name=table_name,
        row_count=count,
        columns=column_names,
    )