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
    col_defs = ", ".join(f'"{c}" VARCHAR' for c in QUOTE_COLUMNS)
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
    db.get_connection().executemany(
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
