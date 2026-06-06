from fastapi import APIRouter, Body, HTTPException, Query

from app.schemas.generation import DatasetResult
from app.services import financial_service

router = APIRouter(prefix="/financial", tags=["financial"])


@router.get("/quote")
async def quote(symbol: str = Query(..., description="Stock symbol (e.g., AAPL)")):
    try:
        return financial_service.get_quote(symbol)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/history")
async def history(
    symbol: str = Query(..., description="Stock symbol (e.g., AAPL)"),
    period: str = Query("1mo", description="Period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max"),
    interval: str = Query("1d", description="Interval: 1m, 2m, 5m, 15m, 30m, 60m, 1d, 5d, 1wk, 1mo"),
):
    try:
        return financial_service.get_history(symbol, period=period, interval=interval)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/batch-to-dataset")
async def batch_to_dataset(
    symbols: list[str] = Body(..., description="List of stock symbols"),
    name: str | None = Body(None, description="Optional dataset name"),
) -> DatasetResult:
    if len(symbols) < 1:
        raise HTTPException(status_code=422, detail="At least one symbol is required")
    if len(symbols) > 50:
        raise HTTPException(status_code=422, detail="Maximum 50 symbols per batch")
    try:
        return financial_service.batch_to_dataset(symbols, name=name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
