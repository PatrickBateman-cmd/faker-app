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


@router.get("/info")
async def info():
    db = DuckDBManager.get_instance()
    datasets = db.execute("SELECT COUNT(*) FROM metadata_datasets").fetchone()[0]
    templates = db.execute("SELECT COUNT(*) FROM metadata_templates").fetchone()[0]
    runs = db.execute("SELECT COUNT(*) FROM metadata_runs").fetchone()[0]
    total_rows = db.execute("SELECT COALESCE(SUM(row_count), 0) FROM metadata_datasets").fetchone()[0]

    recent = db.execute("""
        SELECT name, row_count, created_at FROM metadata_datasets
        ORDER BY created_at DESC LIMIT 5
    """).fetchall()

    return {
        "datasets": datasets,
        "templates": templates,
        "runs": runs,
        "total_rows": total_rows,
        "recent_datasets": [
            {"name": r[0], "rows": r[1], "created_at": str(r[2])} for r in recent
        ],
    }
