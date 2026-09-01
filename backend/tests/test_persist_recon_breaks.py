from __future__ import annotations

from app.services.generation_engine.breaks import BreakRecord
from app.services.generation_engine.persistence import persist_recon_breaks


def test_persist_recon_breaks_writes_rows(db):
    breaks = [
        BreakRecord(
            dataset_id="ds-1", field_name="amount", join_key_value="T1",
            true_value=100.0, broken_value=105.0, break_style="drift",
        ),
        BreakRecord(
            dataset_id="ds-2", field_name="status", join_key_value="T2",
            true_value="settled", broken_value=None, break_style="null",
        ),
    ]
    persist_recon_breaks(db, run_id=7, breaks=breaks)

    rows = db.execute(
        "SELECT run_id, dataset_id, field_name, join_key_value, true_value, broken_value, break_style "
        "FROM metadata_recon_breaks ORDER BY id"
    ).fetchall()
    assert rows == [
        (7, "ds-1", "amount", "T1", "100.0", "105.0", "drift"),
        (7, "ds-2", "status", "T2", "settled", "None", "null"),
    ]


def test_persist_recon_breaks_empty_list_is_noop(db):
    persist_recon_breaks(db, run_id=7, breaks=[])
    count = db.execute("SELECT COUNT(*) FROM metadata_recon_breaks").fetchone()[0]
    assert count == 0
