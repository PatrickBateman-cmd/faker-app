from __future__ import annotations

import json
import uuid
from logging import getLogger

import yfinance as yf

from app.core.database import DuckDBManager
from app.core.validation import validate_column_name, validate_table_name
from app.schemas.generation import DatasetResult

logger = getLogger(__name__)

QUOTE_COLUMNS = [
    "symbol", "shortName", "longName", "regularMarketPrice",
    "previousClose", "change", "changePercent", "dayHigh",
    "dayLow", "volume", "marketCap", "currency",
]

QUOTE_TYPES: dict[str, str] = {
    "symbol": "VARCHAR",
    "shortName": "VARCHAR",
    "longName": "VARCHAR",
    "regularMarketPrice": "DOUBLE",
    "previousClose": "DOUBLE",
    "change": "DOUBLE",
    "changePercent": "DOUBLE",
    "dayHigh": "DOUBLE",
    "dayLow": "DOUBLE",
    "volume": "BIGINT",
    "marketCap": "DOUBLE",
    "currency": "VARCHAR",
}


def _build_quote(symbol: str, info: dict, price: float, prev_close: float | None = None) -> dict:
    if prev_close is None:
        prev_close = float(info.get("previousClose") or price)
    change = round(price - prev_close, 2)
    change_pct = round((change / prev_close) * 100, 2) if prev_close else 0
    return {
        "symbol": symbol.upper(),
        "shortName": info.get("shortName") or symbol.upper(),
        "longName": info.get("longName") or "",
        "regularMarketPrice": price,
        "previousClose": prev_close,
        "change": change,
        "changePercent": change_pct,
        "dayHigh": float(info.get("dayHigh") or 0),
        "dayLow": float(info.get("dayLow") or 0),
        "volume": int(info.get("volume") or 0),
        "marketCap": info.get("marketCap"),
        "currency": info.get("currency") or "USD",
    }


def get_quote(symbol: str) -> dict:
    ticker = yf.Ticker(symbol)
    info = ticker.info or {}
    if info.get("regularMarketPrice"):
        return _build_quote(symbol, info, float(info["regularMarketPrice"]))

    try:
        fi = ticker.fast_info
        price = fi.last_price if hasattr(fi, "last_price") else None
        if price is not None:
            return _build_quote(symbol, info, float(price))
    except (ValueError, KeyError, AttributeError):
        pass

    if info.get("regularMarketPreviousClose"):
        return _build_quote(symbol, info, float(info["regularMarketPreviousClose"]),
                            prev_close=float(info["regularMarketPreviousClose"]))

    raise ValueError(f"No quote data found for symbol '{symbol}'")


def get_history(symbol: str, period: str = "1mo", interval: str = "1d") -> list[dict]:
    ticker = yf.Ticker(symbol)
    try:
        df = ticker.history(period=period, interval=interval)
    except Exception as e:
        raise ValueError(f"Failed to fetch history for '{symbol}': {e}") from e
    if df.empty:
        return []

    df = df.reset_index()
    records: list[dict] = []
    for _, row in df.iterrows():
        records.append({
            "date": str(row["Date"].date()) if hasattr(row["Date"], "date") else str(row["Date"]),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": int(row["Volume"]),
        })
    return records


def batch_to_dataset(symbols: list[str], name: str | None = None) -> DatasetResult:
    dataset_id = str(uuid.uuid4())
    table_name = f"dataset_{dataset_id}"
    validate_table_name(table_name)
    for col in QUOTE_COLUMNS:
        validate_column_name(col)

    db = DuckDBManager.get_instance()
    col_defs = ", ".join(f'"{c}" {QUOTE_TYPES.get(c, "VARCHAR")}' for c in QUOTE_COLUMNS)
    db.execute(f'CREATE TABLE "{table_name}" ({col_defs})')

    rows: list[list[str | float | int | None]] = []
    skipped: list[str] = []
    for symbol in symbols:
        try:
            q = get_quote(symbol.strip())
        except (ValueError, KeyError, AttributeError) as e:
            logger.warning("Skipping symbol '%s': %s", symbol, e)
            skipped.append(symbol.strip())
            continue
        rows.append([q.get(c) for c in QUOTE_COLUMNS])

    if not rows:
        raise ValueError("No valid quote data for any of the requested symbols")

    placeholders = ", ".join("?" for _ in QUOTE_COLUMNS)
    quoted_cols = ", ".join(f'"{c}"' for c in QUOTE_COLUMNS)
    db.executemany(
        f'INSERT INTO "{table_name}" ({quoted_cols}) VALUES ({placeholders})',
        rows,
    )

    count_row = db.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()
    row_count = count_row[0] if count_row else len(rows)
    columns_json = json.dumps(QUOTE_COLUMNS)

    dataset_name = name or f"Financial Batch ({len(rows)} symbols)"
    db.execute(
        """
        INSERT INTO metadata_datasets (dataset_id, run_id, name, table_name, columns_json, row_count, homogeneity, seed)
        VALUES (?, NULL, ?, ?, ?, ?, NULL, NULL)
        """,
        [dataset_id, dataset_name, table_name, columns_json, row_count],
    )

    if skipped:
        logger.info("Fetched %d symbols, skipped: %s", len(rows), ", ".join(skipped))

    return DatasetResult(
        dataset_id=dataset_id,
        name=dataset_name,
        table_name=table_name,
        row_count=row_count,
        columns=QUOTE_COLUMNS,
    )


def enrich_dataset(
    source_dataset_id: str,
    ticker_column: str,
    enrichments: list[dict],
    name: str | None = None,
) -> dict:
    from app.schemas.financial import EnrichmentDef

    parsed = [EnrichmentDef(**e) if isinstance(e, dict) else e for e in enrichments]

    meta = _get_source_dataset(source_dataset_id)
    if not meta:
        raise ValueError(f"Dataset '{source_dataset_id}' not found")

    table_name = validate_table_name(meta["table_name"])
    ticker_col = validate_column_name(ticker_column)
    db = DuckDBManager.get_instance()

    tickers = [
        r[0]
        for r in db.execute(
            f'SELECT DISTINCT "{ticker_col}" FROM "{table_name}"'
        ).fetchall()
        if r[0]
    ]

    lookup: dict[str, dict] = {}
    for symbol in tickers:
        try:
            lookup[symbol] = get_quote(symbol)
        except ValueError:
            logger.warning("Skipping ticker '%s' during enrich", symbol)
            continue

    enrich_cols = [validate_column_name(e.field_name) for e in parsed]

    source_desc = db.execute(f'DESCRIBE "{table_name}"').fetchall()
    source_cols = [r[0] for r in source_desc]
    source_types = {r[0]: r[1] for r in source_desc}

    col_types: dict[str, str] = {}
    for c in source_cols:
        col_types[c] = source_types.get(c, "VARCHAR")
    for c in enrich_cols:
        col_types[c] = QUOTE_TYPES.get(c, "VARCHAR")

    all_cols = source_cols + enrich_cols

    dataset_id = str(uuid.uuid4())
    result_table = f"dataset_{dataset_id}"
    validate_table_name(result_table)

    col_defs = ", ".join(f'"{c}" {col_types[c]}' for c in all_cols)
    db.execute(f'CREATE TABLE "{result_table}" ({col_defs})')

    source_rows = db.execute(f'SELECT * FROM "{table_name}"').fetchall()

    batch: list[list] = []
    for row in source_rows:
        row_dict = dict(zip(source_cols, row, strict=True))
        ticker = row_dict.get(ticker_col, "")
        enrich_vals = lookup.get(ticker, {})
        new_row = list(row) + [enrich_vals.get(e.field_name) for e in parsed]
        batch.append(new_row)

    placeholders = ", ".join("?" for _ in all_cols)
    quoted_cols = ", ".join(f'"{c}"' for c in all_cols)
    db.executemany(
        f'INSERT INTO "{result_table}" ({quoted_cols}) VALUES ({placeholders})',
        batch,
    )

    count_row = db.execute(f'SELECT COUNT(*) FROM "{result_table}"').fetchone()
    row_count = count_row[0] if count_row else len(batch)
    columns_json = json.dumps(all_cols)

    dataset_name = name or f"Enriched {meta['name']}"
    db.execute(
        "INSERT INTO metadata_datasets (dataset_id, run_id, name, table_name, columns_json, row_count, homogeneity, seed) VALUES (?, NULL, ?, ?, ?, ?, NULL, NULL)",
        [dataset_id, dataset_name, result_table, columns_json, row_count],
    )

    from app.schemas.financial import EnrichResponse

    return EnrichResponse(
        dataset_id=dataset_id,
        name=dataset_name,
        table_name=result_table,
        row_count=row_count,
        columns=all_cols,
        source_dataset=source_dataset_id,
    )


def batch_history(symbols: list[str], period: str = "1mo", interval: str = "1d", name: str | None = None) -> DatasetResult:
    dataset_id = str(uuid.uuid4())
    table_name = f"dataset_{dataset_id}"
    validate_table_name(table_name)

    HISTORY_COLUMNS = ["symbol", "date", "open", "high", "low", "close", "volume"]
    HISTORY_TYPES: dict[str, str] = {
        "symbol": "VARCHAR",
        "date": "VARCHAR",
        "open": "DOUBLE",
        "high": "DOUBLE",
        "low": "DOUBLE",
        "close": "DOUBLE",
        "volume": "BIGINT",
    }
    for col in HISTORY_COLUMNS:
        validate_column_name(col)

    db = DuckDBManager.get_instance()
    col_defs = ", ".join(f'"{c}" {HISTORY_TYPES.get(c, "VARCHAR")}' for c in HISTORY_COLUMNS)
    db.execute(f'CREATE TABLE "{table_name}" ({col_defs})')

    all_rows: list[list[str | float | int]] = []
    skipped: list[str] = []

    for symbol in symbols:
        try:
            records = get_history(symbol.strip(), period=period, interval=interval)
        except (ValueError, KeyError, AttributeError) as e:
            logger.warning("Skipping symbol '%s': %s", symbol, e)
            skipped.append(symbol.strip())
            continue
        for rec in records:
            all_rows.append([
                symbol.strip().upper(),
                rec["date"],
                rec["open"],
                rec["high"],
                rec["low"],
                rec["close"],
                rec["volume"],
            ])

    if not all_rows:
        raise ValueError("No history data for any of the requested symbols")

    placeholders = ", ".join("?" for _ in HISTORY_COLUMNS)
    quoted_cols = ", ".join(f'"{c}"' for c in HISTORY_COLUMNS)
    db.executemany(
        f'INSERT INTO "{table_name}" ({quoted_cols}) VALUES ({placeholders})',
        all_rows,
    )

    count_row = db.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()
    row_count = count_row[0] if count_row else len(all_rows)
    columns_json = json.dumps(HISTORY_COLUMNS)

    dataset_name = name or f"Financial History ({len(symbols)} symbols, {period})"
    db.execute(
        """
        INSERT INTO metadata_datasets (dataset_id, run_id, name, table_name, columns_json, row_count, homogeneity, seed)
        VALUES (?, NULL, ?, ?, ?, ?, NULL, NULL)
        """,
        [dataset_id, dataset_name, table_name, columns_json, row_count],
    )

    if skipped:
        logger.info("Fetched history for %d symbols, skipped: %s", len(symbols), ", ".join(skipped))

    return DatasetResult(
        dataset_id=dataset_id,
        name=dataset_name,
        table_name=table_name,
        row_count=row_count,
        columns=HISTORY_COLUMNS,
    )


def _get_source_dataset(dataset_id: str) -> dict | None:
    from app.services.dataset_service import get_dataset

    return get_dataset(dataset_id)
