from __future__ import annotations

import json

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_cli_reconciliation_mode_generates_and_lists_breaks(db):
    fields = json.dumps([
        {"name": "trade_id", "generator": "uuid4", "type": "string"},
        {"name": "amount", "generator": "random_int", "type": "integer",
         "constraint": {"min": 1000, "max": 9999}},
    ])
    datasets_file_content = json.dumps([
        {"name": "gl", "rows": 5, "fields": json.loads(fields)},
        {"name": "subledger", "rows": 5, "fields": json.loads(fields)},
    ])
    import tempfile
    from pathlib import Path

    tmpdir = tempfile.mkdtemp()
    datasets_path = Path(tmpdir) / "datasets.json"
    datasets_path.write_text(datasets_file_content)

    result = runner.invoke(
        app,
        [
            "generate",
            "--name", "recon-test",
            "--datasets-file", str(datasets_path),
            "--reconciliation-mode",
            "--exact-fields", "trade_id,amount",
            "--field-breaks-json", json.dumps([
                {"field_name": "amount", "break_rate": 1.0, "break_style": "drift", "drift_pct": 0.1}
            ]),
            "--seed", "7",
            "--format", "json",
            "--quiet",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    run_id = payload["run_id"]
    assert payload["break_count"] == 5

    breaks_result = runner.invoke(app, ["generate", "breaks", str(run_id), "--format", "json"])
    assert breaks_result.exit_code == 0, breaks_result.output
    records = json.loads(breaks_result.output)
    assert len(records) == 5
    assert all(r["field_name"] == "amount" for r in records)


def test_cli_reconciliation_mode_rejects_explicit_overlap_ratio(db):
    result = runner.invoke(
        app,
        [
            "generate",
            "--name", "recon-test",
            "--fields-json", json.dumps([{"name": "trade_id", "generator": "uuid4", "type": "string"}]),
            "--reconciliation-mode",
            "--exact-fields", "trade_id",
            "--overlap-ratio", "0.5",
            "--quiet",
        ],
    )
    assert result.exit_code == 1
    assert "reconciliation-mode" in result.output.lower()
