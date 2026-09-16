from __future__ import annotations


def test_recon_breaks_table_and_sequence_exist(db):
    db.execute(
        """
        INSERT INTO metadata_recon_breaks
            (run_id, dataset_id, field_name, join_key_value, true_value, broken_value, break_style)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [1, "ds-1", "amount", "T1", "100.0", "105.0", "drift"],
    )
    row = db.execute(
        "SELECT run_id, dataset_id, field_name, break_style FROM metadata_recon_breaks WHERE dataset_id = 'ds-1'"
    ).fetchone()
    assert row == (1, "ds-1", "amount", "drift")


def test_recon_break_id_sequence_increments(db):
    first = db.execute("SELECT nextval('seq_recon_break_id')").fetchone()[0]
    second = db.execute("SELECT nextval('seq_recon_break_id')").fetchone()[0]
    assert second == first + 1
