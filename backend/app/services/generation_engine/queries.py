from __future__ import annotations

from app.core.database import DuckDBManager
from app.schemas.generation import ReconBreakRecord

DEFAULT_RECON_BREAKS_LIMIT = 1000
MAX_RECON_BREAKS_LIMIT = 10000


def get_recon_breaks(
    run_id: int,
    limit: int = DEFAULT_RECON_BREAKS_LIMIT,
    offset: int = 0,
) -> list[ReconBreakRecord]:
    limit = max(1, min(limit, MAX_RECON_BREAKS_LIMIT))
    offset = max(0, offset)
    db = DuckDBManager.get_instance()
    rows = db.execute(
        """
        SELECT id, run_id, dataset_id, field_name, join_key_value,
               true_value, broken_value, break_style, CAST(created_at AS VARCHAR)
        FROM metadata_recon_breaks
        WHERE run_id = ?
        ORDER BY id
        LIMIT ? OFFSET ?
        """,
        [run_id, limit, offset],
    ).fetchall()
    return [
        ReconBreakRecord(
            id=r[0],
            run_id=r[1],
            dataset_id=r[2],
            field_name=r[3],
            join_key_value=r[4],
            true_value=r[5],
            broken_value=r[6],
            break_style=r[7],
            created_at=r[8],
        )
        for r in rows
    ]
