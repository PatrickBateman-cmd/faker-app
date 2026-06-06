from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.core.database import DuckDBManager
from app.services import financial_service


def test_build_quote():
    info = {
        "shortName": "TestCo",
        "longName": "TestCo Inc.",
        "previousClose": 99.0,
        "dayHigh": 101.0,
        "dayLow": 98.0,
        "volume": 1_000_000,
        "marketCap": 1_000_000_000,
        "currency": "USD",
    }
    result = financial_service._build_quote("TEST", info, 100.0)
    assert result["symbol"] == "TEST"
    assert result["regularMarketPrice"] == 100.0
    assert result["change"] == 1.0
    assert result["previousClose"] == 99.0
    assert result["currency"] == "USD"
    assert result["volume"] == 1_000_000


def test_build_quote_without_prev_close():
    info = {"shortName": "TestCo", "currency": "USD"}
    result = financial_service._build_quote("TEST", info, 50.0, prev_close=48.0)
    assert result["change"] == 2.0
    assert result["previousClose"] == 48.0


def test_batch_to_dataset_with_mock(db):
    mock_ticker = MagicMock()
    mock_ticker.info = {
        "shortName": "MockInc",
        "regularMarketPrice": 150.0,
        "previousClose": 148.0,
        "dayHigh": 152.0,
        "dayLow": 147.0,
        "volume": 5_000_000,
        "marketCap": 500_000_000_000,
        "currency": "USD",
    }

    with patch("app.services.financial_service.yf.Ticker", return_value=mock_ticker):
        result = financial_service.batch_to_dataset(["MOCK"], name="mock_batch")

    assert result.row_count == 1
    assert "symbol" in result.columns
    assert "regularMarketPrice" in result.columns


def test_batch_to_dataset_all_skipped(db):
    mock_ticker = MagicMock()
    mock_ticker.info = {}
    mock_ticker.fast_info = MagicMock(last_price=None)

    with patch("app.services.financial_service.yf.Ticker", return_value=mock_ticker):
        with pytest.raises(ValueError, match="No valid quote data"):
            financial_service.batch_to_dataset(["BAD"])


def test_enrich_dataset_with_mock(db):
    ds_id = str(uuid.uuid4())
    table_name = f"dataset_{ds_id}"
    db_conn = DuckDBManager.get_instance()
    db_conn.execute(f'CREATE TABLE "{table_name}" (symbol VARCHAR, price DOUBLE)')
    db_conn.execute(f'INSERT INTO "{table_name}" VALUES (?, ?)', ["TEST", 50.0])
    db_conn.execute(
        "INSERT INTO metadata_datasets (dataset_id, name, table_name, columns_json, row_count) VALUES (?, ?, ?, ?, ?)",
        [ds_id, "source", table_name, json.dumps(["symbol", "price"]), 1],
    )

    mock_ticker = MagicMock()
    mock_ticker.info = {
        "shortName": "EnrichedCo",
        "regularMarketPrice": 100.0,
        "dayHigh": 101.0,
        "dayLow": 99.0,
        "volume": 500_000,
        "marketCap": 500_000_000,
        "currency": "USD",
    }

    with patch("app.services.financial_service.yf.Ticker", return_value=mock_ticker):
        result = financial_service.enrich_dataset(
            ds_id,
            "symbol",
            [{"field_name": "shortName", "source": "quote"}],
            name="enriched",
        )

    assert result.row_count == 1
    assert "shortName" in result.columns
    assert result.name == "enriched"
