# Reconciliation Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `reconciliation_mode` toggle to `/generate` that locks a batch of 2-4 datasets into a guaranteed 1:1:1:1 shared-key join (via the existing overlap-pool mechanism, forced to full coverage) with configurable, per-field, deliberately-introduced value mismatches ("breaks"), and persists a ground-truth record of every break so it can be scored against an external reconciliation tool's output.

**Architecture:** Extends the existing `overlap_ratio`/`exact_fields` pool mechanism (`backend/app/services/generation_engine/{engine,overlap,flat,grouped,row_builder}.py`) rather than building a parallel path. Dataset index 0 in a request is always the authoritative source; datasets 1+ copy pool values verbatim unless a per-row break roll fires, in which case a post-processing step (`breaks.py`) mutates the already-generated row and records a `BreakRecord`. Ground truth is persisted to a new `metadata_recon_breaks` table (own DuckDB sequence) and exposed via a new `GET /generate/runs/{run_id}/breaks` endpoint and a new `faker generate breaks <run_id>` CLI command.

**Tech Stack:** Python 3.14, FastAPI, Pydantic, DuckDB, Typer (existing stack — no new dependencies).

**Spec:** [docs/superpowers/specs/2026-09-01-reconciliation-mode-design.md](../specs/2026-09-01-reconciliation-mode-design.md)

## Global Constraints

- `reconciliation_mode=False` (the default) must leave all existing behavior byte-for-byte unchanged — the existing frontend (`GenerationControls.tsx`) sends neither `reconciliation_mode` nor `field_breaks` and must keep working exactly as today. No frontend files are touched by this plan.
- Validation is raised as plain `ValueError` (not Pydantic validators) — matches the existing style in `engine.py`, and `routers/generation.py` already converts `ValueError` → HTTP 400.
- New DuckDB objects get their **own** sequence (`seq_recon_break_id`) — per CLAUDE.md, never reuse `seq_run_id` or `seq_aggregation_id` for a different entity's primary key.
- All new migration SQL uses `IF NOT EXISTS` and is added as a new entry in `MIGRATIONS` in `backend/app/core/migrations.py` (next one is `"007_recon_breaks"`), consistent with the other 6 entries already there.
- `join_key_field` is always `request.exact_fields[0]` when `reconciliation_mode=True` — never carries a break, and is always copied verbatim across all datasets.
- Run all backend tests from the `backend/` directory with `uv run pytest tests/ -v`; run a single new test file with `uv run pytest tests/<file>.py -v`.

---

### Task 1: Schema additions

**Files:**
- Modify: `backend/app/schemas/generation.py`
- Test: `backend/tests/test_generation_schema.py` (new file)

**Interfaces:**
- Produces: `FieldBreakConfig(field_name: str, break_rate: float = 0.0, break_style: Literal["drift","different","null"] = "drift", drift_pct: float = 0.02)`, `GenerateRequest.reconciliation_mode: bool = False`, `GenerateRequest.field_breaks: list[FieldBreakConfig] = []`, `GenerateResponse.break_count: int = 0`, `ReconBreakRecord(id: int, run_id: int, dataset_id: str, field_name: str, join_key_value: str | None, true_value: str | None, broken_value: str | None, break_style: str, created_at: str)`. Later tasks (2, 4-9) import all of these from `app.schemas.generation`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_generation_schema.py`:

```python
from __future__ import annotations

from app.schemas.generation import (
    FieldBreakConfig,
    GenerateRequest,
    GenerateResponse,
    ReconBreakRecord,
)


def test_generate_request_defaults_are_backward_compatible():
    req = GenerateRequest(datasets=[])
    assert req.reconciliation_mode is False
    assert req.field_breaks == []


def test_field_break_config_defaults():
    cfg = FieldBreakConfig(field_name="amount")
    assert cfg.break_rate == 0.0
    assert cfg.break_style == "drift"
    assert cfg.drift_pct == 0.02


def test_generate_response_break_count_defaults_zero():
    resp = GenerateResponse(run_id=1, homogeneity=50, seed=None, datasets=[])
    assert resp.break_count == 0


def test_recon_break_record_round_trip():
    rec = ReconBreakRecord(
        id=1,
        run_id=1,
        dataset_id="abc",
        field_name="amount",
        join_key_value="T1",
        true_value="100.0",
        broken_value="105.0",
        break_style="drift",
        created_at="2026-09-01T00:00:00",
    )
    assert rec.field_name == "amount"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_generation_schema.py -v`
Expected: FAIL — `ImportError: cannot import name 'FieldBreakConfig'` (or `ReconBreakRecord`).

- [ ] **Step 3: Implement the schema additions**

Edit `backend/app/schemas/generation.py`. Add `from typing import Literal` to the top import, then add after `SharedKeyConfig`:

```python
class FieldBreakConfig(BaseModel):
    field_name: str
    break_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    break_style: Literal["drift", "different", "null"] = "drift"
    drift_pct: float = Field(default=0.02, gt=0.0, le=1.0)
```

Change `GenerateRequest` to:

```python
class GenerateRequest(BaseModel):
    datasets: list[DatasetDefinition] = Field(
        ..., min_length=1, max_length=4
    )
    homogeneity: int = Field(default=50, ge=1, le=100)
    seed: int | None = None
    overlap_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    exact_fields: list[str] = Field(default_factory=list)
    reconciliation_mode: bool = False
    field_breaks: list[FieldBreakConfig] = Field(default_factory=list)
```

Change `GenerateResponse` to add one field at the end:

```python
class GenerateResponse(BaseModel):
    run_id: int
    homogeneity: int
    seed: int | None
    datasets: list[DatasetResult]
    overlap_pool_size: int = 0
    exact_fields: list[str] = Field(default_factory=list)
    break_count: int = 0
```

Add at the end of the file:

```python
class ReconBreakRecord(BaseModel):
    id: int
    run_id: int
    dataset_id: str
    field_name: str
    join_key_value: str | None
    true_value: str | None
    broken_value: str | None
    break_style: str
    created_at: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_generation_schema.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full existing generation test suite to confirm no regression**

Run: `cd backend && uv run pytest tests/test_generation.py -v`
Expected: PASS (all existing tests, unchanged)

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/generation.py backend/tests/test_generation_schema.py
git commit -m "feat: add reconciliation_mode and field_breaks schema fields"
```

---

### Task 2: `metadata_recon_breaks` migration

**Files:**
- Modify: `backend/app/core/migrations.py`
- Test: `backend/tests/test_migrations.py` (new file)

**Interfaces:**
- Consumes: nothing from prior tasks.
- Produces: DuckDB table `metadata_recon_breaks(id, run_id, dataset_id, field_name, join_key_value, true_value, broken_value, break_style, created_at)` and sequence `seq_recon_break_id`. Task 6 (`persistence.py`) and Task 8 (`queries.py`) write to and read from this table by name.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_migrations.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_migrations.py -v`
Expected: FAIL — `duckdb.CatalogException: Table with name metadata_recon_breaks does not exist`

- [ ] **Step 3: Add the migration**

Edit `backend/app/core/migrations.py`, add a new tuple at the end of the `MIGRATIONS` list (after `"006_aggregation_sequence"`, before the closing `]`):

```python
    (
        "007_recon_breaks",
        """
        CREATE SEQUENCE IF NOT EXISTS seq_recon_break_id START 1;
        CREATE TABLE IF NOT EXISTS metadata_recon_breaks (
            id BIGINT PRIMARY KEY DEFAULT nextval('seq_recon_break_id'),
            run_id BIGINT NOT NULL,
            dataset_id VARCHAR NOT NULL,
            field_name VARCHAR NOT NULL,
            join_key_value VARCHAR,
            true_value VARCHAR,
            broken_value VARCHAR,
            break_style VARCHAR NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """,
    ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_migrations.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/migrations.py backend/tests/test_migrations.py
git commit -m "feat: add metadata_recon_breaks table migration"
```

---

### Task 3: Break application logic (`breaks.py`)

**Files:**
- Create: `backend/app/services/generation_engine/breaks.py`
- Test: `backend/tests/test_breaks.py` (new file)

**Interfaces:**
- Consumes: `FieldDefinition`, `FieldBreakConfig` from `app.schemas.generation` (Task 1); `generate_field_value` from `app.services.generation_engine.generators` (existing).
- Produces: `BreakRecord` (dataclass: `dataset_id, field_name, join_key_value, true_value, broken_value, break_style`) and `apply_field_breaks(row: list, fields: list[FieldDefinition], field_breaks: dict[str, FieldBreakConfig], join_key_value: object, dataset_id: str, fake: Faker) -> list[BreakRecord]` — mutates `row` in place for any field that breaks, returns the list of breaks that fired. Tasks 5, 6, and 7 call this.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_breaks.py`:

```python
from __future__ import annotations

import random

from faker import Faker

from app.schemas.generation import FieldBreakConfig, FieldDefinition
from app.services.generation_engine.breaks import BreakRecord, apply_field_breaks


def _fields():
    return [
        FieldDefinition(name="trade_id", generator="uuid4", type="string"),
        FieldDefinition(name="amount", generator="pydecimal", type="float"),
        FieldDefinition(name="status", generator="random_element", type="string"),
    ]


def test_break_rate_zero_never_fires():
    random.seed(1)
    fake = Faker()
    fake.seed_instance(1)
    fields = _fields()
    row = ["T1", 1000.0, "settled"]
    breaks = apply_field_breaks(
        row, fields, {"amount": FieldBreakConfig(field_name="amount", break_rate=0.0)},
        join_key_value="T1", dataset_id="ds-1", fake=fake,
    )
    assert breaks == []
    assert row == ["T1", 1000.0, "settled"]


def test_break_rate_one_always_fires_and_records():
    random.seed(1)
    fake = Faker()
    fake.seed_instance(1)
    fields = _fields()
    row = ["T1", 1000.0, "settled"]
    breaks = apply_field_breaks(
        row, fields,
        {"amount": FieldBreakConfig(field_name="amount", break_rate=1.0, break_style="drift", drift_pct=0.1)},
        join_key_value="T1", dataset_id="ds-1", fake=fake,
    )
    assert len(breaks) == 1
    rec = breaks[0]
    assert isinstance(rec, BreakRecord)
    assert rec.field_name == "amount"
    assert rec.dataset_id == "ds-1"
    assert rec.join_key_value == "T1"
    assert rec.true_value == 1000.0
    assert rec.broken_value == row[1]
    assert abs(row[1] - 1000.0) <= 1000.0 * 0.1 + 1e-6


def test_break_style_null_sets_none():
    random.seed(1)
    fake = Faker()
    fake.seed_instance(1)
    fields = _fields()
    row = ["T1", 1000.0, "settled"]
    breaks = apply_field_breaks(
        row, fields, {"amount": FieldBreakConfig(field_name="amount", break_rate=1.0, break_style="null")},
        join_key_value="T1", dataset_id="ds-1", fake=fake,
    )
    assert breaks[0].broken_value is None
    assert row[1] is None


def test_only_configured_fields_are_eligible():
    random.seed(1)
    fake = Faker()
    fake.seed_instance(1)
    fields = _fields()
    row = ["T1", 1000.0, "settled"]
    breaks = apply_field_breaks(
        row, fields, {"status": FieldBreakConfig(field_name="status", break_rate=1.0, break_style="null")},
        join_key_value="T1", dataset_id="ds-1", fake=fake,
    )
    assert len(breaks) == 1
    assert breaks[0].field_name == "status"
    assert row[1] == 1000.0  # amount untouched
    assert row[2] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_breaks.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.generation_engine.breaks'`

- [ ] **Step 3: Implement `breaks.py`**

Create `backend/app/services/generation_engine/breaks.py`:

```python
from __future__ import annotations

import random
from dataclasses import dataclass

from faker import Faker

from app.schemas.generation import FieldBreakConfig, FieldDefinition
from app.services.generation_engine.generators import generate_field_value


@dataclass
class BreakRecord:
    dataset_id: str
    field_name: str
    join_key_value: object
    true_value: object
    broken_value: object
    break_style: str


def _transform(true_value: object, field: FieldDefinition, cfg: FieldBreakConfig, fake: Faker) -> object:
    if cfg.break_style == "null":
        return None
    if cfg.break_style == "drift":
        delta = true_value * cfg.drift_pct * random.uniform(-1.0, 1.0)
        drifted = true_value + delta
        return round(drifted, 6) if isinstance(true_value, float) else int(round(drifted))
    return generate_field_value(fake, field, field.constraint)


def apply_field_breaks(
    row: list,
    fields: list[FieldDefinition],
    field_breaks: dict[str, FieldBreakConfig],
    join_key_value: object,
    dataset_id: str,
    fake: Faker,
) -> list[BreakRecord]:
    breaks: list[BreakRecord] = []
    for fi, field in enumerate(fields):
        cfg = field_breaks.get(field.name)
        if cfg is None or random.random() >= cfg.break_rate:
            continue
        true_value = row[fi]
        row[fi] = _transform(true_value, field, cfg, fake)
        breaks.append(
            BreakRecord(
                dataset_id=dataset_id,
                field_name=field.name,
                join_key_value=join_key_value,
                true_value=true_value,
                broken_value=row[fi],
                break_style=cfg.break_style,
            )
        )
    return breaks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_breaks.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/generation_engine/breaks.py backend/tests/test_breaks.py
git commit -m "feat: add field-break transform logic for reconciliation mode"
```

---

### Task 4: Ground-truth persistence (`persistence.py`)

**Files:**
- Modify: `backend/app/services/generation_engine/persistence.py`
- Test: `backend/tests/test_persist_recon_breaks.py` (new file)

**Interfaces:**
- Consumes: `BreakRecord` from `app.services.generation_engine.breaks` (Task 3); the `metadata_recon_breaks` table (Task 2).
- Produces: `persist_recon_breaks(db, run_id: int, breaks: list[BreakRecord]) -> None`. Task 7 (`engine.py`) calls this.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_persist_recon_breaks.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_persist_recon_breaks.py -v`
Expected: FAIL — `ImportError: cannot import name 'persist_recon_breaks'`

- [ ] **Step 3: Implement `persist_recon_breaks`**

Edit `backend/app/services/generation_engine/persistence.py`. Add to the imports at the top:

```python
from app.services.generation_engine.breaks import BreakRecord
```

Add at the end of the file:

```python
def persist_recon_breaks(db, run_id: int, breaks: list[BreakRecord]) -> None:
    if not breaks:
        return
    rows = [
        [
            run_id,
            b.dataset_id,
            b.field_name,
            str(b.join_key_value),
            str(b.true_value),
            str(b.broken_value),
            b.break_style,
        ]
        for b in breaks
    ]
    db.executemany(
        """
        INSERT INTO metadata_recon_breaks
            (run_id, dataset_id, field_name, join_key_value, true_value, broken_value, break_style)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_persist_recon_breaks.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/generation_engine/persistence.py backend/tests/test_persist_recon_breaks.py
git commit -m "feat: persist reconciliation ground truth to metadata_recon_breaks"
```

---

### Task 5: Wire breaks into flat dataset generation

**Files:**
- Modify: `backend/app/services/generation_engine/flat.py`
- Test: extend `backend/tests/test_generation.py`

**Interfaces:**
- Consumes: `apply_field_breaks`, `BreakRecord` from `app.services.generation_engine.breaks` (Task 3).
- Produces: `generate_dataset(..., join_key_field: str | None = None, field_breaks: dict[str, FieldBreakConfig] | None = None, ground_truth: list[BreakRecord] | None = None)`. Task 7 (`engine.py`) calls this with the new keyword arguments.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_generation.py`:

```python
def test_flat_field_breaks_applied_to_non_authoritative_dataset(db):
    from app.schemas.generation import FieldBreakConfig

    shared_fields = [
        FieldDefinition(name="trade_id", generator="uuid4", type="string"),
        FieldDefinition(
            name="amount", generator="random_int", type="integer",
            constraint=ConstraintConfig(min=10000, max=99999),
        ),
    ]
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(name="gl", rows=20, fields=list(shared_fields)),
            DatasetDefinition(name="subledger", rows=20, fields=list(shared_fields)),
        ],
        homogeneity=100,
        seed=42,
        overlap_ratio=1.0,
        exact_fields=["trade_id", "amount"],
        reconciliation_mode=True,
        field_breaks=[
            FieldBreakConfig(field_name="amount", break_rate=1.0, break_style="drift", drift_pct=0.1)
        ],
    )
    resp = generate_datasets(req)

    trade_ids_0 = [r[0] for r in db.execute(f'SELECT trade_id FROM "{resp.datasets[0].table_name}"').fetchall()]
    trade_ids_1 = [r[0] for r in db.execute(f'SELECT trade_id FROM "{resp.datasets[1].table_name}"').fetchall()]
    assert trade_ids_0 == trade_ids_1  # join key never breaks

    amounts_0 = [r[0] for r in db.execute(f'SELECT amount FROM "{resp.datasets[0].table_name}"').fetchall()]
    amounts_1 = [r[0] for r in db.execute(f'SELECT amount FROM "{resp.datasets[1].table_name}"').fetchall()]
    for true_v, broken_v in zip(amounts_0, amounts_1, strict=True):
        assert abs(broken_v - true_v) <= true_v * 0.1 + 1

    assert resp.break_count == 20  # one non-authoritative dataset, break_rate=1.0, 20 rows
    gt_rows = db.execute("SELECT COUNT(*) FROM metadata_recon_breaks WHERE run_id = ?", [resp.run_id]).fetchone()[0]
    assert gt_rows == 20


def test_flat_field_breaks_zero_rate_no_ground_truth(db):
    from app.schemas.generation import FieldBreakConfig

    shared_fields = [
        FieldDefinition(name="trade_id", generator="uuid4", type="string"),
        FieldDefinition(name="amount", generator="random_int", type="integer"),
    ]
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(name="gl", rows=10, fields=list(shared_fields)),
            DatasetDefinition(name="subledger", rows=10, fields=list(shared_fields)),
        ],
        homogeneity=100,
        seed=42,
        exact_fields=["trade_id", "amount"],
        reconciliation_mode=True,
        field_breaks=[FieldBreakConfig(field_name="amount", break_rate=0.0)],
    )
    resp = generate_datasets(req)
    amounts_0 = [r[0] for r in db.execute(f'SELECT amount FROM "{resp.datasets[0].table_name}"').fetchall()]
    amounts_1 = [r[0] for r in db.execute(f'SELECT amount FROM "{resp.datasets[1].table_name}"').fetchall()]
    assert amounts_0 == amounts_1
    assert resp.break_count == 0
```

Add `ConstraintConfig` to the existing `from app.schemas.generation import (...)` block at the top of `test_generation.py` if not already imported (it is — check the file; it's already in the Task-1-era import list from the head we read).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_generation.py -k field_breaks -v`
Expected: FAIL — `reconciliation_mode requires at least 2 datasets` is not raised, but more fundamentally `TypeError: generate_dataset() got an unexpected keyword argument` will surface once Task 7 exists; until Task 7, this test fails simply because `reconciliation_mode`/`field_breaks` are accepted by the schema (Task 1) but have no effect yet — `break_count` will be `0` and amounts will match by coincidence or not at all. Confirm it fails with an assertion error (not an import error), which confirms Tasks 1-4 are wired but Task 5-7 are not yet.

- [ ] **Step 3: Implement the wiring in `flat.py`**

Edit `backend/app/services/generation_engine/flat.py`. Add to imports:

```python
from app.schemas.generation import DatasetDefinition, DatasetResult, FieldBreakConfig
from app.services.generation_engine.breaks import BreakRecord, apply_field_breaks
```

Change the function signature:

```python
def generate_dataset(
    fake: Faker,
    definition: DatasetDefinition,
    run_id: int,
    homogeneity: int,
    master_seed: int,
    overlap_pool: list[dict] | None = None,
    exact_field_names: set[str] | None = None,
    join_key_field: str | None = None,
    field_breaks: dict[str, FieldBreakConfig] | None = None,
    ground_truth: list[BreakRecord] | None = None,
) -> DatasetResult:
```

Right after `column_names = [validate_column_name(f.name) for f in fields]` (flat.py:38), add:

```python
    join_key_col_idx = column_names.index(join_key_field) if join_key_field else None
```

In the row loop, replace:

```python
            row = generate_row(
                fields,
                field_fakers,
                fake,
                pool_entry={**sql_entry, **pool_entry},
                shared_key_pool=shared_key_pool,
            )
            batch_data.append(row)
```

with:

```python
            row = generate_row(
                fields,
                field_fakers,
                fake,
                pool_entry={**sql_entry, **pool_entry},
                shared_key_pool=shared_key_pool,
            )
            if field_breaks and join_key_col_idx is not None:
                row_breaks = apply_field_breaks(
                    row, fields, field_breaks, row[join_key_col_idx], dataset_id, fake
                )
                if ground_truth is not None:
                    ground_truth.extend(row_breaks)
            batch_data.append(row)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_generation.py -k field_breaks -v`
Expected: still FAIL at this point — `field_breaks` never reaches `generate_dataset` because `engine.py` (Task 7) doesn't build/pass `join_key_field`/`field_breaks`/`ground_truth` yet, and `reconciliation_mode` validation doesn't exist yet either. **This is expected** — this task only wires the flat-generation half; Task 7 completes the chain. Confirm no `TypeError` — the new keyword-only parameters have defaults so existing calls (from the not-yet-updated `engine.py`) still work.

Run the full pre-existing suite to confirm zero regressions from the signature change:

Run: `cd backend && uv run pytest tests/test_generation.py -v`
Expected: all prior tests PASS (the two new ones remain failing until Task 7 — that's fine, they'll be re-verified there).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/generation_engine/flat.py backend/tests/test_generation.py
git commit -m "feat: apply field breaks after row generation in flat datasets"
```

---

### Task 6: Wire breaks into grouped dataset generation

**Files:**
- Modify: `backend/app/services/generation_engine/grouped.py`
- Test: extend `backend/tests/test_generation.py`

**Interfaces:**
- Consumes: `apply_field_breaks`, `BreakRecord` (Task 3).
- Produces: `generate_grouped_dataset(..., join_key_field: str | None = None, field_breaks: dict[str, FieldBreakConfig] | None = None, ground_truth: list[BreakRecord] | None = None)`. Task 7 calls this with the new keyword arguments, only for child-level join keys/breaks (parent fields are never eligible, matching the existing parent-field overlap restriction).

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_generation.py`:

```python
def test_grouped_field_breaks_applied_to_child_field(db):
    from app.schemas.generation import FieldBreakConfig

    def _grouped_def(name: str) -> DatasetDefinition:
        return DatasetDefinition(
            name=name,
            rows=10,
            group_config=GroupConfig(
                num_groups=2,
                split_pct=100,
                parent_fields=[FieldDefinition(name="trade_id", generator="uuid4", type="string")],
                child_fields=[
                    FieldDefinition(name="counterparty_id", generator="uuid4", type="string"),
                    FieldDefinition(
                        name="qty", generator="random_int", type="integer",
                        constraint=ConstraintConfig(min=1000, max=9999),
                    ),
                ],
            ),
        )

    req = GenerateRequest(
        datasets=[_grouped_def("g1"), _grouped_def("g2")],
        homogeneity=100,
        seed=42,
        overlap_ratio=1.0,
        exact_fields=["counterparty_id", "qty"],
        reconciliation_mode=True,
        field_breaks=[FieldBreakConfig(field_name="qty", break_rate=1.0, break_style="drift", drift_pct=0.1)],
    )
    resp = generate_datasets(req)

    cp_0 = [r[0] for r in db.execute(f'SELECT counterparty_id FROM "{resp.datasets[0].table_name}"').fetchall()]
    cp_1 = [r[0] for r in db.execute(f'SELECT counterparty_id FROM "{resp.datasets[1].table_name}"').fetchall()]
    assert cp_0 == cp_1  # join key never breaks

    qty_0 = [r[0] for r in db.execute(f'SELECT qty FROM "{resp.datasets[0].table_name}"').fetchall()]
    qty_1 = [r[0] for r in db.execute(f'SELECT qty FROM "{resp.datasets[1].table_name}"').fetchall()]
    for true_v, broken_v in zip(qty_0, qty_1, strict=True):
        assert abs(broken_v - true_v) <= true_v * 0.1 + 1

    assert resp.break_count == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_generation.py -k grouped_field_breaks -v`
Expected: FAIL (same reason as Task 5 Step 4 — `engine.py` doesn't pass the new args yet).

- [ ] **Step 3: Implement the wiring in `grouped.py`**

Edit `backend/app/services/generation_engine/grouped.py`. Add to imports:

```python
from app.schemas.generation import DatasetDefinition, DatasetResult, FieldBreakConfig
from app.services.generation_engine.breaks import BreakRecord, apply_field_breaks
```

Change the function signature:

```python
def generate_grouped_dataset(
    fake: Faker,
    definition: DatasetDefinition,
    run_id: int,
    homogeneity: int,
    master_seed: int,
    overlap_pool: list[dict] | None = None,
    exact_field_names: set[str] | None = None,
    join_key_field: str | None = None,
    field_breaks: dict[str, FieldBreakConfig] | None = None,
    ground_truth: list[BreakRecord] | None = None,
) -> DatasetResult:
```

Right after `child_fakers = fakers_from_seeds(child_seeds)` (grouped.py:60), add:

```python
    child_field_names = [f.name for f in child_fields]
    join_key_col_idx = (
        child_field_names.index(join_key_field)
        if join_key_field and join_key_field in child_field_names
        else None
    )
```

There are two call sites that build `child_row` and append to `batch_data` — the grouped loop (grouped.py:119-122) and the flat-rows loop (grouped.py:134-137). In **both**, right after `child_row = generate_row(...)` and before the `batch_data.append(...)` line, add:

```python
                if field_breaks and join_key_col_idx is not None:
                    row_breaks = apply_field_breaks(
                        child_row, child_fields, field_breaks, child_row[join_key_col_idx], dataset_id, fake
                    )
                    if ground_truth is not None:
                        ground_truth.extend(row_breaks)
```

(Indentation must match the surrounding block — 16 spaces inside the grouped `for g_idx` / inner `for _ in range(child_count)` loop, 8 spaces inside the flat-rows `for _ in range(flat_rows)` loop.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_generation.py -k grouped_field_breaks -v`
Expected: still FAIL — same reason, `engine.py` (Task 7) not yet updated. Confirm no `TypeError`.

Run the full pre-existing suite to confirm zero regressions:

Run: `cd backend && uv run pytest tests/test_generation.py -v`
Expected: all prior tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/generation_engine/grouped.py backend/tests/test_generation.py
git commit -m "feat: apply field breaks to child rows in grouped datasets"
```

---

### Task 7: Locking validation + full wiring in `engine.py`

**Files:**
- Modify: `backend/app/services/generation_engine/engine.py`
- Test: `backend/tests/test_generation.py` (Tasks 5 & 6 tests now pass; add validation tests)

**Interfaces:**
- Consumes: everything from Tasks 1-6 (`FieldBreakConfig`, `BreakRecord`, `apply_field_breaks`, `persist_recon_breaks`, the updated `generate_dataset`/`generate_grouped_dataset` signatures).
- Produces: `generate_datasets(request) -> GenerateResponse` now honors `reconciliation_mode`/`field_breaks` and populates `GenerateResponse.break_count`. This is the function Task 8's router and Task 9's CLI already call.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_generation.py`:

```python
def test_reconciliation_mode_requires_two_datasets(db):
    import pytest
    from app.schemas.generation import FieldBreakConfig

    req = GenerateRequest(
        datasets=[DatasetDefinition(name="ds1", rows=5, fields=[FieldDefinition(name="trade_id", generator="uuid4", type="string")])],
        reconciliation_mode=True,
        exact_fields=["trade_id"],
    )
    with pytest.raises(ValueError, match="at least 2 datasets"):
        generate_datasets(req)


def test_reconciliation_mode_requires_exact_fields(db):
    import pytest

    req = GenerateRequest(
        datasets=[
            DatasetDefinition(name="ds1", rows=5, fields=[FieldDefinition(name="trade_id", generator="uuid4", type="string")]),
            DatasetDefinition(name="ds2", rows=5, fields=[FieldDefinition(name="trade_id", generator="uuid4", type="string")]),
        ],
        reconciliation_mode=True,
    )
    with pytest.raises(ValueError, match="requires exact_fields"):
        generate_datasets(req)


def test_field_breaks_without_reconciliation_mode_rejected(db):
    import pytest
    from app.schemas.generation import FieldBreakConfig

    shared_fields = [FieldDefinition(name="trade_id", generator="uuid4", type="string")]
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(name="ds1", rows=5, fields=list(shared_fields)),
            DatasetDefinition(name="ds2", rows=5, fields=list(shared_fields)),
        ],
        field_breaks=[FieldBreakConfig(field_name="trade_id", break_rate=0.1)],
    )
    with pytest.raises(ValueError, match="requires reconciliation_mode"):
        generate_datasets(req)


def test_field_break_on_join_key_rejected(db):
    import pytest
    from app.schemas.generation import FieldBreakConfig

    shared_fields = [FieldDefinition(name="trade_id", generator="uuid4", type="string")]
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(name="ds1", rows=5, fields=list(shared_fields)),
            DatasetDefinition(name="ds2", rows=5, fields=list(shared_fields)),
        ],
        reconciliation_mode=True,
        exact_fields=["trade_id"],
        field_breaks=[FieldBreakConfig(field_name="trade_id", break_rate=0.1)],
    )
    with pytest.raises(ValueError, match="cannot target the join key"):
        generate_datasets(req)


def test_field_break_not_in_exact_fields_rejected(db):
    import pytest
    from app.schemas.generation import FieldBreakConfig

    shared_fields = [
        FieldDefinition(name="trade_id", generator="uuid4", type="string"),
        FieldDefinition(name="notes", generator="text", type="string"),
    ]
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(name="ds1", rows=5, fields=list(shared_fields)),
            DatasetDefinition(name="ds2", rows=5, fields=list(shared_fields)),
        ],
        reconciliation_mode=True,
        exact_fields=["trade_id"],
        field_breaks=[FieldBreakConfig(field_name="notes", break_rate=0.1)],
    )
    with pytest.raises(ValueError, match="must be listed in exact_fields"):
        generate_datasets(req)


def test_field_break_drift_on_non_numeric_field_rejected(db):
    import pytest
    from app.schemas.generation import FieldBreakConfig

    shared_fields = [
        FieldDefinition(name="trade_id", generator="uuid4", type="string"),
        FieldDefinition(name="status", generator="random_element", type="string"),
    ]
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(name="ds1", rows=5, fields=list(shared_fields)),
            DatasetDefinition(name="ds2", rows=5, fields=list(shared_fields)),
        ],
        reconciliation_mode=True,
        exact_fields=["trade_id", "status"],
        field_breaks=[FieldBreakConfig(field_name="status", break_rate=0.1, break_style="drift")],
    )
    with pytest.raises(ValueError, match="not numeric"):
        generate_datasets(req)


def test_reconciliation_mode_forces_overlap_ratio_to_one(db):
    shared_fields = [FieldDefinition(name="trade_id", generator="uuid4", type="string")]
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(name="ds1", rows=8, fields=list(shared_fields)),
            DatasetDefinition(name="ds2", rows=8, fields=list(shared_fields)),
        ],
        reconciliation_mode=True,
        exact_fields=["trade_id"],
        overlap_ratio=0.0,  # deliberately not 1.0 — must be forced
    )
    resp = generate_datasets(req)
    assert resp.overlap_pool_size == 8
```

- [ ] **Step 2: Run all new/pending tests to verify failure**

Run: `cd backend && uv run pytest tests/test_generation.py -k "reconciliation or field_break or grouped_field_breaks" -v`
Expected: FAIL — `reconciliation_mode` has no effect yet in `engine.py` (no `ValueError`s raised, `overlap_pool_size` stays 0, earlier tasks' tests still failing).

- [ ] **Step 3: Implement the full wiring in `engine.py`**

Replace the entire contents of `backend/app/services/generation_engine/engine.py` with:

```python
from __future__ import annotations

import random

from faker import Faker

from app.core.database import DuckDBManager
from app.schemas.generation import DatasetResult, FieldBreakConfig, GenerateRequest, GenerateResponse
from app.services.generation_engine.breaks import BreakRecord
from app.services.generation_engine.flat import generate_dataset
from app.services.generation_engine.grouped import generate_grouped_dataset
from app.services.generation_engine.overlap import build_overlap_pool, effective_fields
from app.services.generation_engine.persistence import persist_recon_breaks

_NUMERIC_TYPES = {"integer", "int", "float", "decimal", "number"}


def generate_datasets(request: GenerateRequest) -> GenerateResponse:
    master_seed = request.seed if request.seed is not None else random.randint(0, 2**31 - 1)
    main_fake = Faker()
    main_fake.seed_instance(master_seed)
    random.seed(master_seed)

    overlap_ratio = request.overlap_ratio
    exact_field_names = set(request.exact_fields)

    join_key_field: str | None = None
    field_breaks_by_name: dict[str, FieldBreakConfig] = {}
    if request.reconciliation_mode:
        if len(request.datasets) < 2:
            raise ValueError("reconciliation_mode requires at least 2 datasets")
        if not request.exact_fields:
            raise ValueError("reconciliation_mode requires exact_fields (join key first)")
        overlap_ratio = 1.0
        join_key_field = request.exact_fields[0]
        for fb in request.field_breaks:
            if fb.field_name not in exact_field_names:
                raise ValueError(f"field_breaks field '{fb.field_name}' must be listed in exact_fields")
            if fb.field_name == join_key_field:
                raise ValueError(f"field_breaks cannot target the join key field '{join_key_field}'")
            if fb.break_style == "drift":
                for ds in request.datasets:
                    target = next((f for f in effective_fields(ds) if f.name == fb.field_name), None)
                    if target is not None and target.type.lower() not in _NUMERIC_TYPES:
                        raise ValueError(
                            f"field_breaks '{fb.field_name}' uses break_style='drift' but field type "
                            f"'{target.type}' is not numeric in dataset '{ds.name}'"
                        )
            field_breaks_by_name[fb.field_name] = fb
    elif request.field_breaks:
        raise ValueError("field_breaks requires reconciliation_mode=True")

    # Validate overlap config before touching DuckDB
    if overlap_ratio > 0:
        if not exact_field_names:
            raise ValueError("exact_fields must be specified when overlap_ratio > 0")
        for ds in request.datasets:
            if ds.group_config:
                parent_names = {f.name for f in ds.group_config.parent_fields}
                for ef in exact_field_names:
                    if ef in parent_names:
                        raise ValueError(
                            f"exact field '{ef}' is a parent field in grouped dataset '{ds.name}'; "
                            "overlap only supports child-level fields for grouped datasets"
                        )
            ds_field_names = {f.name for f in effective_fields(ds)}
            for ef in exact_field_names:
                if ef not in ds_field_names:
                    raise ValueError(f"exact field '{ef}' not found in dataset '{ds.name}'")

    db = DuckDBManager.get_instance()
    result = db.execute("SELECT nextval('seq_run_id')").fetchone()
    run_id = result[0] if result else 1

    # Build the global overlap pool once
    overlap_pool: list[dict] = []
    pool_size = 0
    if overlap_ratio > 0 and request.datasets:
        pool_size = int(min(d.rows for d in request.datasets) * overlap_ratio)
        if pool_size > 0:
            first_fields = effective_fields(request.datasets[0])
            overlap_pool = build_overlap_pool(main_fake, first_fields, exact_field_names, pool_size)

    ground_truth: list[BreakRecord] = []
    dataset_results: list[DatasetResult] = []
    for idx, dataset_def in enumerate(request.datasets):
        ds_field_breaks = field_breaks_by_name if idx > 0 else {}
        if dataset_def.group_config:
            dr = generate_grouped_dataset(
                fake=main_fake,
                definition=dataset_def,
                run_id=run_id,
                homogeneity=request.homogeneity,
                master_seed=master_seed,
                overlap_pool=overlap_pool,
                exact_field_names=exact_field_names,
                join_key_field=join_key_field,
                field_breaks=ds_field_breaks,
                ground_truth=ground_truth,
            )
        else:
            dr = generate_dataset(
                fake=main_fake,
                definition=dataset_def,
                run_id=run_id,
                homogeneity=request.homogeneity,
                master_seed=master_seed,
                overlap_pool=overlap_pool,
                exact_field_names=exact_field_names,
                join_key_field=join_key_field,
                field_breaks=ds_field_breaks,
                ground_truth=ground_truth,
            )
        dataset_results.append(dr)

    if ground_truth:
        persist_recon_breaks(db, run_id, ground_truth)

    return GenerateResponse(
        run_id=run_id,
        homogeneity=request.homogeneity,
        seed=master_seed,
        datasets=dataset_results,
        overlap_pool_size=pool_size,
        exact_fields=list(exact_field_names),
        break_count=len(ground_truth),
    )
```

- [ ] **Step 4: Run the full generation test suite**

Run: `cd backend && uv run pytest tests/test_generation.py -v`
Expected: PASS — every test in the file, including all Task 5, 6, and 7 tests and every pre-existing overlap/grouped/shared_key test.

- [ ] **Step 5: Run the complete backend suite**

Run: `cd backend && uv run pytest tests/ -v`
Expected: PASS (all tests, no regressions anywhere in the 40+ backend tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/generation_engine/engine.py backend/tests/test_generation.py
git commit -m "feat: lock reconciliation_mode validation and wire breaks end-to-end"
```

---

### Task 8: Ground-truth query service + `GET /generate/runs/{run_id}/breaks`

**Files:**
- Create: `backend/app/services/generation_engine/queries.py`
- Modify: `backend/app/services/generation_engine/__init__.py`
- Modify: `backend/app/routers/generation.py`
- Test: `backend/tests/test_api.py` (extend) or a new `backend/tests/test_recon_breaks_api.py`

**Interfaces:**
- Consumes: `ReconBreakRecord` (Task 1), `metadata_recon_breaks` table (Task 2).
- Produces: `get_recon_breaks(run_id: int) -> list[ReconBreakRecord]`, exported from `app.services.generation_engine`; `GET /generate/runs/{run_id}/breaks`. Task 9 (CLI) calls `get_recon_breaks` directly.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_recon_breaks_api.py`:

```python
from __future__ import annotations


def test_get_breaks_empty_for_unknown_run(client):
    resp = client.get("/generate/runs/999999/breaks")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_breaks_returns_persisted_records(client):
    gen_resp = client.post(
        "/generate",
        json={
            "datasets": [
                {"name": "gl", "rows": 5, "fields": [
                    {"name": "trade_id", "generator": "uuid4", "type": "string"},
                    {"name": "amount", "generator": "random_int", "type": "integer",
                     "constraint": {"min": 1000, "max": 9999}},
                ]},
                {"name": "subledger", "rows": 5, "fields": [
                    {"name": "trade_id", "generator": "uuid4", "type": "string"},
                    {"name": "amount", "generator": "random_int", "type": "integer",
                     "constraint": {"min": 1000, "max": 9999}},
                ]},
            ],
            "homogeneity": 100,
            "seed": 7,
            "reconciliation_mode": True,
            "exact_fields": ["trade_id", "amount"],
            "field_breaks": [{"field_name": "amount", "break_rate": 1.0, "break_style": "drift", "drift_pct": 0.1}],
        },
    )
    assert gen_resp.status_code == 200
    run_id = gen_resp.json()["run_id"]
    break_count = gen_resp.json()["break_count"]
    assert break_count == 5

    breaks_resp = client.get(f"/generate/runs/{run_id}/breaks")
    assert breaks_resp.status_code == 200
    records = breaks_resp.json()
    assert len(records) == 5
    assert all(r["field_name"] == "amount" for r in records)
    assert all(r["run_id"] == run_id for r in records)
```

Routers are included with `prefix=""` in `backend/app/main.py` (the `/api` prefix in CLAUDE.md is a frontend Vite-proxy concern, stripped before reaching the backend) — existing tests in `test_api.py` call `client.post("/generate", ...)` directly, confirming this.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_recon_breaks_api.py -v`
Expected: FAIL — `404 Not Found` for `GET .../breaks` (route doesn't exist yet).

- [ ] **Step 3: Implement the query function**

Create `backend/app/services/generation_engine/queries.py`:

```python
from __future__ import annotations

from app.core.database import DuckDBManager
from app.schemas.generation import ReconBreakRecord


def get_recon_breaks(run_id: int) -> list[ReconBreakRecord]:
    db = DuckDBManager.get_instance()
    rows = db.execute(
        """
        SELECT id, run_id, dataset_id, field_name, join_key_value,
               true_value, broken_value, break_style, CAST(created_at AS VARCHAR)
        FROM metadata_recon_breaks
        WHERE run_id = ?
        ORDER BY id
        """,
        [run_id],
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
```

Edit `backend/app/services/generation_engine/__init__.py` to:

```python
from app.services.generation_engine.engine import generate_datasets
from app.services.generation_engine.queries import get_recon_breaks

__all__ = ["generate_datasets", "get_recon_breaks"]
```

Edit `backend/app/routers/generation.py`, add after the existing `generate` route:

```python
@router.get("/runs/{run_id}/breaks")
async def get_breaks(run_id: int):
    return generation_engine.get_recon_breaks(run_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_recon_breaks_api.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && uv run pytest tests/ -v`
Expected: PASS (all tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/generation_engine/queries.py backend/app/services/generation_engine/__init__.py backend/app/routers/generation.py backend/tests/test_recon_breaks_api.py
git commit -m "feat: add GET /generate/runs/{run_id}/breaks endpoint"
```

---

### Task 9: CLI support

**Files:**
- Modify: `backend/cli/generate.py`
- Test: `backend/tests/test_cli_reconciliation.py` (new file)

**Interfaces:**
- Consumes: `GenerateRequest`, `FieldBreakConfig` (Task 1), `generation_engine.generate_datasets` / `generation_engine.get_recon_breaks` (Tasks 7 & 8).
- Produces: `--reconciliation-mode`, `--exact-fields`, `--overlap-ratio` flags on `faker generate`; new `faker generate breaks <run_id>` command. Nothing downstream depends on this — it's the final task.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_cli_reconciliation.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_cli_reconciliation.py -v`
Expected: FAIL — `No such option: --reconciliation-mode`.

- [ ] **Step 3: Implement the CLI flags and `breaks` command**

Edit `backend/cli/generate.py`. Add to the imports:

```python
from app.schemas.generation import (
    ConstraintConfig,
    DatasetDefinition,
    FieldBreakConfig,
    FieldDefinition,
    GenerateRequest,
    GroupConfig,
)
from app.services import generation_engine
from app.services.generation_engine import generate_datasets
```

(Keep the existing `from app.services.generation_engine import generate_datasets` import — add the `generation_engine` module import alongside it so `generation_engine.get_recon_breaks` is reachable in the new command.)

Add new parameters to the `generate` callback signature (after `db: str = typer.Option(...)`):

```python
    reconciliation_mode: bool = typer.Option(False, "--reconciliation-mode", help="Lock this batch into reconciliation mode: full overlap + optional intentional breaks"),
    exact_fields: str = typer.Option(None, "--exact-fields", help="Comma-separated field names shared across datasets; first is the join key"),
    overlap_ratio: float = typer.Option(0.0, "--overlap-ratio", help="Fraction of rows drawn from the shared pool (0.0-1.0)", min=0.0, max=1.0),
    field_breaks_json: str = typer.Option(None, "--field-breaks-json", help="Inline JSON list of field break configs (requires --reconciliation-mode)"),
```

Right after the `dataset_defs = [_parse_dataset_def(d) for d in defs_data]` line, add:

```python
    if reconciliation_mode and overlap_ratio != 0.0:
        console.print("[red]Error:[/red] --overlap-ratio cannot be combined with --reconciliation-mode (it is forced to 1.0 automatically)")
        raise typer.Exit(code=1)

    exact_fields_list = [s.strip() for s in exact_fields.split(",") if s.strip()] if exact_fields else []
    field_breaks_list = (
        [FieldBreakConfig(**fb) for fb in json.loads(field_breaks_json)] if field_breaks_json else []
    )
```

Change the `request = GenerateRequest(...)` construction to:

```python
    request = GenerateRequest(
        datasets=dataset_defs,
        homogeneity=homogeneity,
        seed=seed,
        overlap_ratio=overlap_ratio,
        exact_fields=exact_fields_list,
        reconciliation_mode=reconciliation_mode,
        field_breaks=field_breaks_list,
    )
```

Add a new command at the end of the file (after `_constraint_to_dict`):

```python
@app.command("breaks")
def breaks_cmd(
    run_id: int = typer.Argument(..., help="Run ID returned by `faker generate`"),
    fmt: str = typer.Option("table", "--format", "-f", help="Output format"),
    db: str = typer.Option(None, "--db", "-d", help="DuckDB path override"),
) -> None:
    """Show the reconciliation ground truth (intentional breaks) for a run."""
    state = get_state()
    state.ensure_db(db=db)

    records = generation_engine.get_recon_breaks(run_id)
    rows_out = [
        [str(r.id), r.dataset_id, r.field_name, str(r.join_key_value), str(r.true_value), str(r.broken_value), r.break_style]
        for r in records
    ]
    output_result(
        f"Reconciliation breaks for run {run_id} ({len(records)})",
        ["ID", "Dataset", "Field", "Join Key", "True Value", "Broken Value", "Style"],
        rows_out,
        fmt,
        json_data=[r.model_dump() for r in records],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_cli_reconciliation.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the complete backend suite one final time**

Run: `cd backend && uv run pytest tests/ -v`
Expected: PASS (all tests — this is the last task, so this is the final regression check for the whole feature).

- [ ] **Step 6: Typecheck (frontend is untouched, but confirm nothing else broke)**

Run: `cd backend && uv run faker generate --help`
Expected: help text prints and includes `--reconciliation-mode`, `--exact-fields`, `--overlap-ratio`, `--field-breaks-json` without error.

- [ ] **Step 7: Commit**

```bash
git add backend/cli/generate.py backend/tests/test_cli_reconciliation.py
git commit -m "feat: add reconciliation-mode CLI flags and generate breaks command"
```

---

## Self-Review Notes

- **Spec coverage:** Schema/API (Task 1), locking validation table (Task 7), break application + `_transform` styles (Task 3), engine wiring for flat (Task 5) and grouped (Task 6), ground truth persistence (Task 4) and migration (Task 2), API endpoint (Task 8), CLI (Task 9) — every section of the spec maps to a task.
- **Placeholder scan:** no TBDs; every step has concrete code.
- **Type consistency:** `FieldBreakConfig`, `BreakRecord`, `ReconBreakRecord`, `apply_field_breaks`, `persist_recon_breaks`, `get_recon_breaks` are named and typed identically everywhere they're defined (Tasks 1, 3, 4, 8) and consumed (Tasks 5, 6, 7, 9).
- Tasks 5 and 6's new tests are expected to stay red until Task 7 lands — this is called out explicitly in each task's Step 4 so an executor doesn't mistake it for a bug in their own work.
