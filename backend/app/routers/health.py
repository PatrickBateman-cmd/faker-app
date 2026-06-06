from fastapi import APIRouter

from app.core.database import DuckDBManager

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    try:
        db = DuckDBManager.get_instance()
        db.execute("SELECT 1")
        return {"status": "ok", "version": "0.1.0", "duckdb": "connected"}
    except Exception:
        return {"status": "degraded", "version": "0.1.0", "duckdb": "disconnected"}
