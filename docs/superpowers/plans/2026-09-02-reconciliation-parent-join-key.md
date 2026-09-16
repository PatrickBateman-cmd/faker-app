# Reconciliation Parent Join Key Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix a diagnosed frontend bug in the Field Breaks UI, then let `reconciliation_mode`'s join key (`exact_fields[0]`) be a parent-level field when every dataset in the batch is grouped with matching `num_groups`, `rows`, and `split_pct=100` — the natural case for trade/transaction data where the shared business key (e.g. `transaction_id`) lives on the parent, not the child.

**Architecture:** Extends the existing `overlap_ratio`/`exact_fields`/`reconciliation_mode` machinery (`backend/app/services/generation_engine/{engine,overlap,grouped}.py`) with a second, group-indexed pool alongside the existing row-indexed one, plus deterministic group sizing so the two pools' boundaries stay aligned across datasets. Frontend gets one bug fix (unrelated root cause, same feature area) and one small hint-text correction.

**Tech Stack:** Python 3.14, FastAPI, Pydantic, DuckDB (backend); React 19, TypeScript (frontend) — existing stack, no new dependencies.

**Spec:** [docs/superpowers/specs/2026-09-01-reconciliation-mode-parent-join-key-design.md](../specs/2026-09-01-reconciliation-mode-parent-join-key-design.md)

## Global Constraints

- No new request/response API fields, no new CLI flags — this plan only changes what the existing `reconciliation_mode` + `exact_fields` combination is allowed to mean, and fixes a frontend bug.
- `reconciliation_mode` with a child-level join key (today's only supported case) must remain byte-for-byte unchanged — every new check is additive and only fires when the join key is actually parent-level.
- Backend validation is raised as plain `ValueError` (matches the existing style in `engine.py`; `routers/generation.py` converts `ValueError` → HTTP 400).
- `field_breaks` and non-join-key `exact_fields` remain child-level fields only — no parent-level break mechanism is introduced.
- Flat-vs-grouped reconciliation is out of scope — a parent-level join key requires every dataset in the batch to be grouped.
- Backend tests run with `cd backend && uv run pytest tests/<file>.py -v`; the full suite is `cd backend && uv run pytest tests/ -v`. Follow the existing `db` pytest fixture pattern used throughout `backend/tests/test_generation.py` (temp DuckDB, migrations auto-applied) — do not invent a different test style.
- Frontend has no automated test infra beyond a ThemeSwitcher smoke test (per this repo's CLAUDE.md) — frontend tasks are verified with `cd frontend && ./node_modules/.bin/tsc --noEmit` and `npm run build`, plus a manual trace of the new guard logic in the task's own steps.

---

### Task 1: Frontend — require a join key before Field Breaks can be added

**Files:**
- Modify: `frontend/src/components/GenerationControls/GenerationControls.tsx`

**Interfaces:**
- Consumes: nothing new — uses the existing `exactFields` state string and `eligibleFieldNames()` helper already defined in this file.
- Produces: nothing new for other tasks — this is a self-contained UI fix.

**Root cause:** `addFieldBreak()` (current lines 270-278) and the Field Breaks dropdown's `onChange` (current lines 442-448) both auto-sync a chosen break field into the free-text `exactFields` state via `setExactFields((prev) => (prev.trim() ? \`${prev}, ${candidate}\` : candidate))`. When `exactFields` is empty, the chosen break field becomes the *only* — and therefore first, i.e. join-key — entry. The dropdown then excludes the join key (current line 453) from every row's options, so that field silently disappears from what's selectable. This is the "two fields, only one shows in the dropdown" bug.

**Fix:** add a new precondition to the Field Breaks panel — if there are eligible fields but no join key is set yet, tell the user to set one first and disable "+ Add break rule". This makes the empty-`exactFields` auto-sync path unreachable (the button that triggers it is disabled), which is sufficient — no change to the auto-sync logic itself is needed.

- [ ] **Step 1: Make the change**

In `GenerationControls.tsx`, find this block (current lines 428-437):

```tsx
          <p className="text-xs font-semibold text-[var(--accent)] uppercase tracking-wider">Field Breaks</p>
          {eligibleFieldNames(datasets[0]).length === 0 ? (
            <p className="text-xs text-[var(--red)]">
              {mode === "grouped"
                ? "No child fields yet — move at least one field from Parent Fields to Child Fields to add a break rule."
                : "Add at least one field to the first dataset to add a break rule."}
            </p>
          ) : fieldBreaks.length === 0 ? (
            <p className="text-xs text-[var(--muted)]">No break rules — datasets will match exactly on the fields above.</p>
          ) : null}
```

Replace it with:

```tsx
          <p className="text-xs font-semibold text-[var(--accent)] uppercase tracking-wider">Field Breaks</p>
          {eligibleFieldNames(datasets[0]).length === 0 ? (
            <p className="text-xs text-[var(--red)]">
              {mode === "grouped"
                ? "No child fields yet — move at least one field from Parent Fields to Child Fields to add a break rule."
                : "Add at least one field to the first dataset to add a break rule."}
            </p>
          ) : !exactFields.split(",").map((s) => s.trim()).filter(Boolean)[0] ? (
            <p className="text-xs text-[var(--red)]">
              Set a join key in Exact Fields above before adding break rules.
            </p>
          ) : fieldBreaks.length === 0 ? (
            <p className="text-xs text-[var(--muted)]">No break rules — datasets will match exactly on the fields above.</p>
          ) : null}
```

Then find the "+ Add break rule" button (current lines 500-506):

```tsx
          <button
            onClick={addFieldBreak}
            disabled={eligibleFieldNames(datasets[0]).length === 0}
            className="self-start text-xs text-[var(--muted)] hover:text-[var(--text)] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            + Add break rule
          </button>
```

Replace the `disabled` condition:

```tsx
          <button
            onClick={addFieldBreak}
            disabled={
              eligibleFieldNames(datasets[0]).length === 0 ||
              !exactFields.split(",").map((s) => s.trim()).filter(Boolean)[0]
            }
            className="self-start text-xs text-[var(--muted)] hover:text-[var(--text)] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            + Add break rule
          </button>
```

- [ ] **Step 2: Verify with typecheck and build**

Run: `cd frontend && ./node_modules/.bin/tsc --noEmit`
Expected: no output (clean).

Run: `cd frontend && npm run build`
Expected: `✓ built in <time>` with no errors.

- [ ] **Step 3: Manually trace the fix**

Confirm by reading the code (no browser needed): with `exactFields` empty and `eligibleFieldNames(datasets[0])` non-empty, the new middle branch renders the "Set a join key..." message and the button's `disabled` expression evaluates to `true` (since `!undefined` is `true`) — so `addFieldBreak()` cannot fire, and the empty-`exactFields` auto-sync path in that function is now unreachable from the UI. Once the user types a join key into Exact Fields, the button re-enables and the panel falls through to the existing "no break rules" / row-rendering branches, unchanged.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/GenerationControls/GenerationControls.tsx
git commit -m "fix: require a join key before Field Breaks can be added"
```

---

### Task 2: Backend — allow a parent-level join key in validation

**Files:**
- Modify: `backend/app/services/generation_engine/engine.py`
- Test: `backend/tests/test_generation.py` (extend)

**Interfaces:**
- Consumes: nothing new.
- Produces: a `join_key_is_parent: bool` local variable in `generate_datasets()`, set `True` only when the join key is validated as consistently parent-level across every dataset. Task 4 consumes this to decide whether to build a parent pool and pass `deterministic_group_sizes`.

This task only adds the *validation* — negative-path tests only. A request that passes this new validation will still not actually produce matching join-key values until Task 4 lands (the pool-building/wiring isn't done yet); that's expected and is why this task's tests only cover the rejection paths.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_generation.py`:

```python
def _grouped_def_with_parent_key(name: str, num_groups: int = 4, split_pct: float = 100, rows: int = 20) -> DatasetDefinition:
    return DatasetDefinition(
        name=name,
        rows=rows,
        group_config=GroupConfig(
            num_groups=num_groups,
            split_pct=split_pct,
            parent_fields=[FieldDefinition(name="transaction_id", generator="uuid4", type="string")],
            child_fields=[
                FieldDefinition(
                    name="amount", generator="random_int", type="integer",
                    constraint=ConstraintConfig(min=1000, max=9999),
                ),
            ],
        ),
    )


def test_parent_join_key_rejects_flat_dataset_in_batch(db):
    import pytest

    flat_def = DatasetDefinition(
        name="flat_ds", rows=20,
        fields=[FieldDefinition(name="transaction_id", generator="uuid4", type="string")],
    )
    req = GenerateRequest(
        datasets=[_grouped_def_with_parent_key("gl"), flat_def],
        homogeneity=100,
        seed=42,
        reconciliation_mode=True,
        exact_fields=["transaction_id"],
    )
    with pytest.raises(ValueError, match="requires every dataset to be grouped"):
        generate_datasets(req)


def test_parent_join_key_rejects_child_designation_on_other_dataset(db):
    import pytest

    mismatched_def = DatasetDefinition(
        name="subledger", rows=20,
        group_config=GroupConfig(
            num_groups=4,
            split_pct=100,
            parent_fields=[FieldDefinition(name="other_parent", generator="word", type="string")],
            child_fields=[
                FieldDefinition(name="transaction_id", generator="uuid4", type="string"),
                FieldDefinition(
                    name="amount", generator="random_int", type="integer",
                    constraint=ConstraintConfig(min=1000, max=9999),
                ),
            ],
        ),
    )
    req = GenerateRequest(
        datasets=[_grouped_def_with_parent_key("gl"), mismatched_def],
        homogeneity=100,
        seed=42,
        reconciliation_mode=True,
        exact_fields=["transaction_id"],
    )
    with pytest.raises(ValueError, match="requires every dataset to be grouped"):
        generate_datasets(req)


def test_parent_join_key_rejects_num_groups_mismatch(db):
    import pytest

    req = GenerateRequest(
        datasets=[
            _grouped_def_with_parent_key("gl", num_groups=4),
            _grouped_def_with_parent_key("subledger", num_groups=5),
        ],
        homogeneity=100,
        seed=42,
        reconciliation_mode=True,
        exact_fields=["transaction_id"],
    )
    with pytest.raises(ValueError, match="same num_groups"):
        generate_datasets(req)


def test_parent_join_key_rejects_split_pct_not_100(db):
    import pytest

    req = GenerateRequest(
        datasets=[
            _grouped_def_with_parent_key("gl", split_pct=100),
            _grouped_def_with_parent_key("subledger", split_pct=80),
        ],
        homogeneity=100,
        seed=42,
        reconciliation_mode=True,
        exact_fields=["transaction_id"],
    )
    with pytest.raises(ValueError, match="split_pct=100"):
        generate_datasets(req)


def test_child_join_key_validation_unchanged(db):
    # Regression: a plain child-level join key (today's only prior case) must still be rejected
    # if it's actually a parent field — the carve-out must not accidentally widen this check.
    import pytest

    req = GenerateRequest(
        datasets=[_grouped_def_with_parent_key("gl"), _grouped_def_with_parent_key("subledger")],
        homogeneity=100,
        seed=42,
        reconciliation_mode=True,
        exact_fields=["amount", "transaction_id"],  # "amount" (child) is the join key here, "transaction_id" (parent) is not
    )
    with pytest.raises(ValueError, match="parent field"):
        generate_datasets(req)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_generation.py -k parent_join_key -v`
Expected: FAIL — the parent-level join key carve-out doesn't exist yet, so `test_parent_join_key_rejects_flat_dataset_in_batch` etc. either don't raise at all, or raise the wrong (pre-existing "is a parent field") message instead of the new ones. `test_child_join_key_validation_unchanged` should already PASS (it doesn't depend on anything new) — confirm it does, as a baseline.

- [ ] **Step 3: Implement the validation**

Edit `backend/app/services/generation_engine/engine.py`. Change:

```python
    join_key_field: str | None = None
    field_breaks_by_name: dict[str, FieldBreakConfig] = {}
    if request.reconciliation_mode:
        if len(request.datasets) < 2:
            raise ValueError("reconciliation_mode requires at least 2 datasets")
        if not request.exact_fields:
            raise ValueError("reconciliation_mode requires exact_fields (join key first)")
        if len({ds.rows for ds in request.datasets}) > 1:
            raise ValueError("reconciliation_mode requires all datasets to declare the same number of rows")
        overlap_ratio = 1.0
        join_key_field = request.exact_fields[0]
        for fb in request.field_breaks:
```

to:

```python
    join_key_field: str | None = None
    join_key_is_parent = False
    field_breaks_by_name: dict[str, FieldBreakConfig] = {}
    if request.reconciliation_mode:
        if len(request.datasets) < 2:
            raise ValueError("reconciliation_mode requires at least 2 datasets")
        if not request.exact_fields:
            raise ValueError("reconciliation_mode requires exact_fields (join key first)")
        if len({ds.rows for ds in request.datasets}) > 1:
            raise ValueError("reconciliation_mode requires all datasets to declare the same number of rows")
        overlap_ratio = 1.0
        join_key_field = request.exact_fields[0]

        join_key_is_parent = any(
            ds.group_config and join_key_field in {f.name for f in ds.group_config.parent_fields}
            for ds in request.datasets
        )
        if join_key_is_parent:
            for ds in request.datasets:
                parent_names = set() if not ds.group_config else {f.name for f in ds.group_config.parent_fields}
                if not ds.group_config or join_key_field not in parent_names:
                    raise ValueError(
                        f"reconciliation_mode: parent-level join key '{join_key_field}' requires "
                        f"every dataset to be grouped with '{join_key_field}' as a parent field"
                    )
            if len({ds.group_config.num_groups for ds in request.datasets}) > 1:
                raise ValueError(
                    "reconciliation_mode: parent-level join key requires all grouped datasets "
                    "to declare the same num_groups"
                )
            if any(ds.group_config.split_pct != 100 for ds in request.datasets):
                raise ValueError(
                    "reconciliation_mode: parent-level join key requires split_pct=100 "
                    "on every grouped dataset"
                )

        for fb in request.field_breaks:
```

(Every other line inside `if request.reconciliation_mode:` — the `field_breaks` loop and the `field_breaks_by_name[fb.field_name] = fb` line — stays exactly as-is, just now positioned after this new block.)

Then change the overlap-validation loop:

```python
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
```

to:

```python
    # Validate overlap config before touching DuckDB
    if overlap_ratio > 0:
        if not exact_field_names:
            raise ValueError("exact_fields must be specified when overlap_ratio > 0")
        for ds in request.datasets:
            if ds.group_config:
                parent_names = {f.name for f in ds.group_config.parent_fields}
                for ef in exact_field_names:
                    if ef in parent_names and not (join_key_is_parent and ef == join_key_field):
                        raise ValueError(
                            f"exact field '{ef}' is a parent field in grouped dataset '{ds.name}'; "
                            "overlap only supports child-level fields for grouped datasets"
                        )
```

(The rest of that loop — the `ds_field_names`/"not found in dataset" check — is unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_generation.py -k parent_join_key -v`
Expected: PASS (5 tests: the 4 new negative-path tests plus `test_child_join_key_validation_unchanged`).

- [ ] **Step 5: Run the full generation suite to confirm no regressions**

Run: `cd backend && uv run pytest tests/test_generation.py -v`
Expected: PASS — every pre-existing test in the file, unchanged.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/generation_engine/engine.py backend/tests/test_generation.py
git commit -m "feat: validate parent-level join key preconditions for reconciliation_mode"
```

---

### Task 3: Backend — `build_parent_pool` in `overlap.py`

**Files:**
- Modify: `backend/app/services/generation_engine/overlap.py`
- Test: `backend/tests/test_overlap.py` (new file)

**Interfaces:**
- Consumes: `FieldDefinition` (existing, `app.schemas.generation`), `generate_field_value` (existing, `app.services.generation_engine.generators`).
- Produces: `build_parent_pool(fake: Faker, parent_fields: list[FieldDefinition], join_key_field: str, num_groups: int) -> list[dict]`. Task 4 calls this from `engine.py`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_overlap.py`:

```python
from __future__ import annotations

from faker import Faker

from app.schemas.generation import FieldDefinition
from app.services.generation_engine.overlap import build_parent_pool


def test_build_parent_pool_one_entry_per_group():
    fake = Faker()
    fake.seed_instance(42)
    parent_fields = [
        FieldDefinition(name="transaction_id", generator="uuid4", type="string"),
        FieldDefinition(name="other_parent_field", generator="word", type="string"),
    ]
    pool = build_parent_pool(fake, parent_fields, "transaction_id", num_groups=5)
    assert len(pool) == 5
    assert all(set(entry.keys()) == {"transaction_id"} for entry in pool)
    assert len({entry["transaction_id"] for entry in pool}) == 5  # uuid4 values are distinct


def test_build_parent_pool_zero_groups():
    fake = Faker()
    fake.seed_instance(1)
    parent_fields = [FieldDefinition(name="transaction_id", generator="uuid4", type="string")]
    pool = build_parent_pool(fake, parent_fields, "transaction_id", num_groups=0)
    assert pool == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_overlap.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_parent_pool'`.

- [ ] **Step 3: Implement `build_parent_pool`**

Edit `backend/app/services/generation_engine/overlap.py`. Add at the end of the file:

```python
def build_parent_pool(
    fake: Faker,
    parent_fields: list[FieldDefinition],
    join_key_field: str,
    num_groups: int,
) -> list[dict]:
    field = next(f for f in parent_fields if f.name == join_key_field)
    return [{field.name: generate_field_value(fake, field, None)} for _ in range(num_groups)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_overlap.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/generation_engine/overlap.py backend/tests/test_overlap.py
git commit -m "feat: add build_parent_pool for group-indexed join key values"
```

---

### Task 4: Backend — wire the parent pool through `engine.py` and `grouped.py`

**Files:**
- Modify: `backend/app/services/generation_engine/engine.py`
- Modify: `backend/app/services/generation_engine/grouped.py`
- Test: `backend/tests/test_generation.py` (extend)

**Interfaces:**
- Consumes: `build_parent_pool` (Task 3), `join_key_is_parent` (Task 2).
- Produces: `generate_grouped_dataset(..., parent_pool: list[dict] | None = None, deterministic_group_sizes: bool = False)`. Nothing downstream depends on this beyond `engine.py`'s own call site — this is the last task that touches the generation engine.

This is the capstone task: after this lands, a parent-level join key actually produces matching values across datasets, group-by-group, with group boundaries aligned so child-level breaks land in the correct group too.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_generation.py` (reuses `_grouped_def_with_parent_key` from Task 2):

```python
def test_parent_join_key_matches_across_groups(db):
    from app.schemas.generation import FieldBreakConfig

    req = GenerateRequest(
        datasets=[_grouped_def_with_parent_key("gl"), _grouped_def_with_parent_key("subledger")],
        homogeneity=100,
        seed=42,
        reconciliation_mode=True,
        exact_fields=["transaction_id", "amount"],
        field_breaks=[FieldBreakConfig(field_name="amount", break_rate=1.0, break_style="drift", drift_pct=0.1)],
    )
    resp = generate_datasets(req)

    tx_ids_0 = {
        r[0] for r in db.execute(f'SELECT transaction_id FROM "{resp.datasets[0].table_name}"').fetchall()
    }
    tx_ids_1 = {
        r[0] for r in db.execute(f'SELECT transaction_id FROM "{resp.datasets[1].table_name}"').fetchall()
    }
    assert tx_ids_0 == tx_ids_1  # same set of transaction_ids in both datasets
    assert len(tx_ids_0) == 4  # matches num_groups

    assert resp.break_count == 20  # dataset[1]'s 20 child rows all broke on "amount" (break_rate=1.0)


def test_parent_join_key_group_sizes_are_deterministic_and_aligned(db):
    req = GenerateRequest(
        datasets=[_grouped_def_with_parent_key("gl"), _grouped_def_with_parent_key("subledger")],
        homogeneity=100,
        seed=42,
        reconciliation_mode=True,
        exact_fields=["transaction_id"],
    )
    resp = generate_datasets(req)

    def _counts_by_tx(table_name: str) -> dict:
        rows = db.execute(f'SELECT transaction_id FROM "{table_name}"').fetchall()
        counts: dict = {}
        for (tx,) in rows:
            counts[tx] = counts.get(tx, 0) + 1
        return counts

    counts_0 = _counts_by_tx(resp.datasets[0].table_name)
    counts_1 = _counts_by_tx(resp.datasets[1].table_name)
    assert counts_0 == counts_1  # identical child-row count per transaction_id in both datasets


def test_child_join_key_group_sizes_stay_random(db):
    # Regression: a plain child-level join key (the existing, already-shipped case) must NOT
    # switch to deterministic group sizing — this flag is scoped strictly to parent-level keys.
    req = GenerateRequest(
        datasets=[_grouped_def_with_parent_key("gl"), _grouped_def_with_parent_key("subledger")],
        homogeneity=100,
        seed=42,
        overlap_ratio=1.0,
        exact_fields=["amount"],  # child-level join key, no reconciliation_mode
    )
    resp = generate_datasets(req)
    assert resp.datasets[0].row_count == 20
    assert resp.datasets[1].row_count == 20
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_generation.py -k "parent_join_key_matches or group_sizes" -v`
Expected: FAIL — `test_parent_join_key_matches_across_groups` and `test_parent_join_key_group_sizes_are_deterministic_and_aligned` fail because `parent_pool`/`deterministic_group_sizes` don't exist yet, so `transaction_id` is generated independently per dataset (no cross-dataset matching) and group sizes are still randomly distributed. `test_child_join_key_group_sizes_stay_random` should already PASS (pre-existing code path, unaffected) — confirm it does, as a baseline.

- [ ] **Step 3: Implement the wiring**

Edit `backend/app/services/generation_engine/engine.py`. Add `build_parent_pool` to the import:

```python
from app.services.generation_engine.overlap import build_overlap_pool, build_parent_pool, effective_fields
```

Change the pool-building block from:

```python
    # Build the global overlap pool once
    overlap_pool: list[dict] = []
    pool_size = 0
    if overlap_ratio > 0 and request.datasets:
        pool_size = int(min(d.rows for d in request.datasets) * overlap_ratio)
        if pool_size > 0:
            first_fields = effective_fields(request.datasets[0])
            overlap_pool = build_overlap_pool(main_fake, first_fields, exact_field_names, pool_size)
```

to:

```python
    # Build the global overlap pool once
    overlap_pool: list[dict] = []
    pool_size = 0
    parent_pool: list[dict] = []
    row_exact_field_names = exact_field_names
    if join_key_is_parent:
        row_exact_field_names = exact_field_names - {join_key_field}
        first_group_cfg = request.datasets[0].group_config
        assert first_group_cfg is not None
        parent_pool = build_parent_pool(
            main_fake, first_group_cfg.parent_fields, join_key_field, first_group_cfg.num_groups
        )
    if overlap_ratio > 0 and request.datasets:
        pool_size = int(min(d.rows for d in request.datasets) * overlap_ratio)
        if pool_size > 0:
            first_fields = effective_fields(request.datasets[0])
            overlap_pool = build_overlap_pool(main_fake, first_fields, row_exact_field_names, pool_size)
```

Then change the `generate_grouped_dataset` call inside the dataset loop from:

```python
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
```

to:

```python
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
                parent_pool=parent_pool,
                deterministic_group_sizes=join_key_is_parent,
            )
```

Now edit `backend/app/services/generation_engine/grouped.py`. Change the signature from:

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

to:

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
    parent_pool: list[dict] | None = None,
    deterministic_group_sizes: bool = False,
) -> DatasetResult:
```

Change the join-key-index computation block from:

```python
    child_field_names = [f.name for f in child_fields]
    join_key_col_idx = (
        child_field_names.index(join_key_field)
        if join_key_field and join_key_field in child_field_names
        else None
    )
```

to:

```python
    child_field_names = [f.name for f in child_fields]
    join_key_col_idx = (
        child_field_names.index(join_key_field)
        if join_key_field and join_key_field in child_field_names
        else None
    )
    parent_field_names = [f.name for f in parent_fields]
    join_key_in_parent = bool(join_key_field) and join_key_field in parent_field_names
    parent_join_key_idx = parent_field_names.index(join_key_field) if join_key_in_parent else None
    has_join_key_value = join_key_in_parent or join_key_col_idx is not None
```

Change the group-size computation from:

```python
    # Distribute grouped_rows randomly across num_groups.
    # This must be computed before sql_child_columns is sized, since over-generation
    # from the diff-correction/clamping logic below can make sum(group_sizes) > grouped_rows.
    if grouped_enabled:
        raw_weights = [random.random() for _ in range(num_groups)]
        total_weight = sum(raw_weights)
        group_sizes = [max(1, int(grouped_rows * w / total_weight)) for w in raw_weights]
        diff = grouped_rows - sum(group_sizes)
        for i in range(abs(diff)):
            group_sizes[i % num_groups] += 1 if diff > 0 else -1
        group_sizes = [max(1, s) for s in group_sizes]
    else:
        group_sizes = []
```

to:

```python
    # Distribute grouped_rows across num_groups.
    # This must be computed before sql_child_columns is sized, since over-generation
    # from the diff-correction/clamping logic below can make sum(group_sizes) > grouped_rows.
    if grouped_enabled:
        if deterministic_group_sizes:
            base, remainder = divmod(grouped_rows, num_groups)
            group_sizes = [base + (1 if i < remainder else 0) for i in range(num_groups)]
            group_sizes = [max(1, s) for s in group_sizes]
        else:
            raw_weights = [random.random() for _ in range(num_groups)]
            total_weight = sum(raw_weights)
            group_sizes = [max(1, int(grouped_rows * w / total_weight)) for w in raw_weights]
            diff = grouped_rows - sum(group_sizes)
            for i in range(abs(diff)):
                group_sizes[i % num_groups] += 1 if diff > 0 else -1
            group_sizes = [max(1, s) for s in group_sizes]
    else:
        group_sizes = []
```

Change `_next_parent_row` and its grouped-loop call site from:

```python
    def _next_parent_row() -> list:
        nonlocal parent_call_idx
        sql_entry = {name: values[parent_call_idx] for name, values in sql_parent_columns.items()}
        parent_row = generate_row(parent_fields, parent_fakers, fake, pool_entry=sql_entry)
        parent_call_idx += 1
        return parent_row

    if grouped_enabled:
        for g_idx in range(num_groups):
            parent_id = str(uuid.uuid4())
            parent_row = _next_parent_row()
```

to:

```python
    def _next_parent_row(group_idx: int | None = None) -> list:
        nonlocal parent_call_idx
        sql_entry = {name: values[parent_call_idx] for name, values in sql_parent_columns.items()}
        pool_entry = (
            parent_pool[group_idx] if parent_pool and group_idx is not None and group_idx < len(parent_pool) else {}
        )
        parent_row = generate_row(parent_fields, parent_fakers, fake, pool_entry={**sql_entry, **pool_entry})
        parent_call_idx += 1
        return parent_row

    if grouped_enabled:
        for g_idx in range(num_groups):
            parent_id = str(uuid.uuid4())
            parent_row = _next_parent_row(g_idx)
```

(The flat-rows loop's call site, `parent_row = _next_parent_row()`, stays exactly as-is — no `group_idx` — since a flat/ungrouped row has no group.)

Finally, change **both** `apply_field_breaks` call sites (grouped loop and flat-rows loop) from:

```python
                if field_breaks and join_key_col_idx is not None:
                    row_breaks = apply_field_breaks(
                        child_row, child_fields, field_breaks, child_row[join_key_col_idx], dataset_id, fake
                    )
                    if ground_truth is not None:
                        ground_truth.extend(row_breaks)
```

to:

```python
                if field_breaks and has_join_key_value:
                    join_key_value = (
                        parent_row[parent_join_key_idx] if join_key_in_parent else child_row[join_key_col_idx]
                    )
                    row_breaks = apply_field_breaks(
                        child_row, child_fields, field_breaks, join_key_value, dataset_id, fake
                    )
                    if ground_truth is not None:
                        ground_truth.extend(row_breaks)
```

(There are two occurrences of this block — one inside `if grouped_enabled: for g_idx ...: for _ in range(child_count):`, one inside the `# Flat rows` `for _ in range(flat_rows):` loop. Apply the same replacement to both, keeping each occurrence's original indentation.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_generation.py -v`
Expected: PASS — every test in the file, including the 3 new ones from this task, the 5 from Task 2, and every pre-existing test (Task-2-era and the original 9-task reconciliation-mode plan's tests).

- [ ] **Step 5: Run the complete backend suite**

Run: `cd backend && uv run pytest tests/ -v`
Expected: PASS (all tests, no regressions).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/generation_engine/engine.py backend/app/services/generation_engine/grouped.py backend/tests/test_generation.py
git commit -m "feat: support parent-level join key with deterministic group alignment"
```

---

### Task 5: Frontend — exempt the join key from the "parent field" warning

**Files:**
- Modify: `frontend/src/components/GenerationControls/GenerationControls.tsx`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — final task in this plan.

**Context:** the inline red hint added in a previous session (current lines 409-424) flags *any* typed Exact Fields entry that's currently a parent field in a grouped dataset. Now that the backend allows the *first* entry (the join key) to be parent-level, the hint needs to exempt position 0.

- [ ] **Step 1: Make the change**

In `GenerationControls.tsx`, find this block (current lines 409-424):

```tsx
      {mode === "grouped" && (overlapRatio > 0 || reconciliationMode) && (() => {
        const parentNames = new Set(
          (datasets[0]?.group_config?.parent_fields ?? []).map((f) => f.name)
        );
        const invalid = exactFields
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
          .filter((f) => parentNames.has(f));
        return invalid.length > 0 ? (
          <p className="text-xs text-[var(--red)]">
            {invalid.map((f) => `"${f}"`).join(", ")} {invalid.length === 1 ? "is a parent field" : "are parent fields"} — move{" "}
            {invalid.length === 1 ? "it" : "them"} to Child Fields to use for exact fields / breaks.
          </p>
        ) : null;
      })()}
```

Replace it with:

```tsx
      {mode === "grouped" && (overlapRatio > 0 || reconciliationMode) && (() => {
        const parentNames = new Set(
          (datasets[0]?.group_config?.parent_fields ?? []).map((f) => f.name)
        );
        const parsed = exactFields.split(",").map((s) => s.trim()).filter(Boolean);
        // The first entry is the join key. In reconciliation mode it's allowed to be a
        // parent field (see the backend's parent-level join key support); every other
        // entry must still be a child field.
        const checkFrom = reconciliationMode ? 1 : 0;
        const invalid = parsed.slice(checkFrom).filter((f) => parentNames.has(f));
        return invalid.length > 0 ? (
          <p className="text-xs text-[var(--red)]">
            {invalid.map((f) => `"${f}"`).join(", ")} {invalid.length === 1 ? "is a parent field" : "are parent fields"} — move{" "}
            {invalid.length === 1 ? "it" : "them"} to Child Fields to use for exact fields / breaks.
          </p>
        ) : null;
      })()}
```

- [ ] **Step 2: Verify with typecheck and build**

Run: `cd frontend && ./node_modules/.bin/tsc --noEmit`
Expected: no output (clean).

Run: `cd frontend && npm run build`
Expected: `✓ built in <time>` with no errors.

- [ ] **Step 3: Manually trace the fix**

With `reconciliationMode = true` and `exactFields = "transaction_id, amount"` where `transaction_id` is a parent field: `checkFrom = 1`, so `parsed.slice(1)` is `["amount"]` — `transaction_id` is never checked, no warning shown (correct — it's the join key, now allowed). With the plain (non-reconciliation) overlap feature, `reconciliationMode` is `false`, so `checkFrom = 0` and every entry is still checked, including position 0 — unchanged from before, since the plain overlap feature never gained parent-key support.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/GenerationControls/GenerationControls.tsx
git commit -m "fix: exempt the join key from the parent-field warning in reconciliation mode"
```

---

## Self-Review Notes

- **Spec coverage:** Validation carve-out (Task 2), parent pool (Task 3), full wiring + group-size determinism (Task 4), frontend hint fix (Task 5) — every section of the spec maps to a task. The Task 1 bug fix is unrelated to the spec but was explicitly folded into this plan by request.
- **Placeholder scan:** no TBDs; every step has concrete code.
- **Type consistency:** `join_key_is_parent`, `build_parent_pool`, `parent_pool`, `deterministic_group_sizes`, `join_key_in_parent`, `parent_join_key_idx`, `has_join_key_value` are named and typed identically everywhere they're defined (Tasks 2, 3, 4) and consumed (Task 4's engine.py/grouped.py wiring).
- Task 2's tests intentionally do not verify positive (accepted) parent-key requests actually produce correct output — that's Task 4's job, once the pool/wiring exists. Task 2 only proves the validation rules themselves are correct in isolation.
