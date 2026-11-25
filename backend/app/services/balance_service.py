from __future__ import annotations

import json
import random
import uuid

from app.core.database import DuckDBManager
from app.core.validation import validate_column_name
from app.schemas.balance import BalanceDeriveRequest, BalanceDeriveResponse
from app.schemas.generation import FieldBreakConfig
from app.services.dataset_service import get_dataset_table_name, register_transformed_dataset
from app.services.generation_engine.breaks import BreakRecord
from app.services.generation_engine.persistence import persist_recon_breaks

_BALANCE_BREAK_FIELDS = {"closing_balance", "net_movement"}


def _build_balance_sql(
    source_table: str,
    result_table: str,
    account_fields: list[str],
    currency_field: str,
    date_field: str,
    amount_field: str,
    direction_field: str,
    credit_values: list[str],
    debit_values: list[str],
    start_date: str,
    end_date: str,
    opening_balance_seed: float,
) -> tuple[str, list]:
    acct_cols = [f'"{c}"' for c in account_fields]
    acct_select = ", ".join(acct_cols)
    partition_cols = ", ".join([*acct_cols, f'"{currency_field}"'])
    grid_key_cols = [*account_fields, currency_field]

    join_conditions = [f'g."{c}" = d."{c}"' for c in grid_key_cols]
    join_conditions.append("g.day = d.day")
    join_sql = " AND ".join(join_conditions)

    case_parts: list[str] = []
    case_params: list[str] = []
    if credit_values:
        placeholders = ", ".join(["?"] * len(credit_values))
        case_parts.append(f'WHEN "{direction_field}" IN ({placeholders}) THEN "{amount_field}"')
        case_params.extend(credit_values)
    if debit_values:
        placeholders = ", ".join(["?"] * len(debit_values))
        case_parts.append(f'WHEN "{direction_field}" IN ({placeholders}) THEN -"{amount_field}"')
        case_params.extend(debit_values)
    case_sql = "CASE " + " ".join(case_parts) + " ELSE 0.0 END"

    joined_select = ", ".join(f'g."{c}"' for c in grid_key_cols)

    sql = f"""
        CREATE TABLE "{result_table}" AS
        WITH accounts AS (
            SELECT DISTINCT {acct_select}, "{currency_field}"
            FROM "{source_table}"
        ),
        spine AS (
            SELECT CAST(unnest(generate_series(CAST(? AS DATE), CAST(? AS DATE), INTERVAL 1 DAY)) AS DATE) AS day
        ),
        grid AS (
            SELECT a.*, s.day FROM accounts a CROSS JOIN spine s
        ),
        daily AS (
            SELECT {acct_select}, "{currency_field}",
                   CAST("{date_field}" AS DATE) AS day,
                   SUM({case_sql}) AS net_movement
            FROM "{source_table}"
            WHERE CAST("{date_field}" AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
            GROUP BY {acct_select}, "{currency_field}", CAST("{date_field}" AS DATE)
        ),
        joined AS (
            SELECT {joined_select}, g.day,
                   COALESCE(d.net_movement, 0.0) AS net_movement
            FROM grid g
            LEFT JOIN daily d ON {join_sql}
        )
        SELECT {acct_select}, "{currency_field}", day, net_movement,
               CAST(? AS DOUBLE) + COALESCE(SUM(net_movement) OVER (
                   PARTITION BY {partition_cols}
                   ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
               ), 0.0) AS opening_balance,
               CAST(? AS DOUBLE) + SUM(net_movement) OVER (
                   PARTITION BY {partition_cols}
                   ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
               ) AS closing_balance
        FROM joined
        ORDER BY {partition_cols}, day
    """
    params = [
        start_date,
        end_date,
        *case_params,
        start_date,
        end_date,
        opening_balance_seed,
        opening_balance_seed,
    ]
    return sql, params


def _perturb_balance_value(true_value: float, style: str, drift_pct: float) -> float | None:
    if style == "null":
        return None
    if style == "drift":
        draw = random.uniform(-1.0, 1.0)
        sign = 1 if draw >= 0 else -1
        if true_value == 0:
            drifted = sign * max(1.0, drift_pct * 100)
        else:
            drifted = true_value + true_value * drift_pct * draw
        result = round(float(drifted), 6)
        if result == true_value:
            result = round(true_value + sign * max(abs(true_value) * drift_pct, 1e-6), 6)
        return result
    # "different": a materially larger, uncontrolled perturbation -- there is no Faker
    # generator to redraw a balance from, so this represents a plausible-looking but
    # substantially wrong value rather than a small drift.
    magnitude = max(abs(true_value), 1.0)
    result = round(true_value + random.uniform(-1.0, 1.0) * magnitude * random.uniform(0.5, 2.0), 6)
    if result == true_value:
        result += magnitude
    return result


def _apply_balance_breaks(
    db,
    result_dataset_id: str,
    result_table: str,
    account_fields: list[str],
    currency_field: str,
    balance_breaks: list[FieldBreakConfig],
) -> list[BreakRecord]:
    breaks_by_field: dict[str, FieldBreakConfig] = {}
    for cfg in balance_breaks:
        if cfg.field_name not in _BALANCE_BREAK_FIELDS:
            msg = f"balance_breaks field '{cfg.field_name}' must be one of {sorted(_BALANCE_BREAK_FIELDS)}"
            raise ValueError(msg)
        breaks_by_field[cfg.field_name] = cfg
    if not breaks_by_field:
        return []

    key_cols = [*account_fields, currency_field, "day"]
    key_select = ", ".join(f'"{c}"' for c in key_cols)
    field_select = ", ".join(f'"{f}"' for f in breaks_by_field)
    rows = db.execute(f'SELECT {key_select}, {field_select} FROM "{result_table}"').fetchall()

    n_keys = len(key_cols)
    ground_truth: list[BreakRecord] = []
    updates: dict[str, list[list]] = {f: [] for f in breaks_by_field}

    for row in rows:
        key_values = list(row[:n_keys])
        join_key_value = "|".join(str(v) for v in key_values)
        for offset, field_name in enumerate(breaks_by_field):
            cfg = breaks_by_field[field_name]
            true_value = row[n_keys + offset]
            if true_value is None or random.random() >= cfg.break_rate:
                continue
            broken_value = _perturb_balance_value(float(true_value), cfg.break_style, cfg.drift_pct)
            updates[field_name].append([broken_value, *key_values])
            ground_truth.append(
                BreakRecord(
                    dataset_id=result_dataset_id,
                    field_name=field_name,
                    join_key_value=join_key_value,
                    true_value=true_value,
                    broken_value=broken_value,
                    break_style=cfg.break_style,
                )
            )

    where_clause = " AND ".join(f'"{c}" = ?' for c in key_cols)
    for field_name, batch in updates.items():
        if not batch:
            continue
        db.executemany(f'UPDATE "{result_table}" SET "{field_name}" = ? WHERE {where_clause}', batch)

    return ground_truth


def derive_balances(source_dataset_id: str, request: BalanceDeriveRequest) -> BalanceDeriveResponse:
    table_name = get_dataset_table_name(source_dataset_id)
    if not table_name:
        msg = f"Source dataset '{source_dataset_id}' not found"
        raise LookupError(msg)

    account_fields = [validate_column_name(c) for c in request.account_fields]
    currency_field = validate_column_name(request.currency_field)
    date_field = validate_column_name(request.date_field)
    amount_field = validate_column_name(request.amount_field)
    direction_field = validate_column_name(request.direction_field)

    if not request.credit_values and not request.debit_values:
        msg = "At least one of credit_values/debit_values must be non-empty"
        raise ValueError(msg)

    db = DuckDBManager.get_instance()

    start_date = request.start_date
    end_date = request.end_date
    if start_date is None or end_date is None:
        bounds = db.execute(
            f'SELECT MIN(CAST("{date_field}" AS DATE)), MAX(CAST("{date_field}" AS DATE)) FROM "{table_name}"'
        ).fetchone()
        if not bounds or bounds[0] is None:
            msg = f"Source dataset '{source_dataset_id}' has no rows in '{date_field}'"
            raise ValueError(msg)
        start_date = start_date or str(bounds[0])
        end_date = end_date or str(bounds[1])

    opening_balance_seed = (
        request.opening_balance_seed
        if request.opening_balance_seed is not None
        else random.uniform(1_000, 100_000)
    )

    result_id = str(uuid.uuid4())
    result_table = f"dataset_{result_id}"

    sql, params = _build_balance_sql(
        source_table=table_name,
        result_table=result_table,
        account_fields=account_fields,
        currency_field=currency_field,
        date_field=date_field,
        amount_field=amount_field,
        direction_field=direction_field,
        credit_values=request.credit_values,
        debit_values=request.debit_values,
        start_date=start_date,
        end_date=end_date,
        opening_balance_seed=opening_balance_seed,
    )

    columns = [*account_fields, currency_field, "day", "net_movement", "opening_balance", "closing_balance"]
    ground_truth: list[BreakRecord] = []
    run_id: int | None = None

    with db.transaction():
        db.execute(sql, params)

        if request.balance_breaks:
            ground_truth = _apply_balance_breaks(
                db, result_id, result_table, account_fields, currency_field, request.balance_breaks
            )
            if ground_truth:
                run_id_row = db.execute("SELECT nextval('seq_run_id')").fetchone()
                run_id = run_id_row[0] if run_id_row else None
                persist_recon_breaks(db, run_id, ground_truth)

        count_row = db.execute(f'SELECT COUNT(*) FROM "{result_table}"').fetchone()
        actual_count = count_row[0] if count_row else 0

        register_transformed_dataset(result_id, request.name, result_table, columns, actual_count)

        db.execute(
            """
            INSERT INTO metadata_aggregations (id, source_dataset, name, config_json)
            VALUES (nextval('seq_aggregation_id'), ?, ?, ?)
            """,
            [
                source_dataset_id,
                request.name,
                json.dumps({"transform_type": "balance", **request.model_dump()}),
            ],
        )

    return BalanceDeriveResponse(
        dataset_id=result_id,
        name=request.name,
        table_name=result_table,
        row_count=actual_count,
        columns=columns,
        source_dataset=source_dataset_id,
        opening_balance_seed=opening_balance_seed,
        start_date=str(start_date),
        end_date=str(end_date),
        run_id=run_id,
        break_count=len(ground_truth),
    )
