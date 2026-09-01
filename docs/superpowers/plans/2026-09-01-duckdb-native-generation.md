# DuckDB-Native Generation Fast Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give 5 "boring" scalar generators (`random_int`, `pyint`, `pydecimal`, `boolean`, `uuid4`, `uuid_int`) a DuckDB-native bulk-SQL fast path, while every other generator and every cross-field feature (`condition`, `formula`, `shared_key`, overlap pools) keeps using the existing Python row loop unchanged.

**Architecture:** A new `sql_generators.py` module classifies fields as SQL-eligible or not, and bulk-generates eligible fields as plain Python lists via one parameterized DuckDB query per field (verified against the installed DuckDB 1.5.3 — `setseed()` is deterministic and reproducible, and per-column independent seeding requires separate statements, not one multi-column `SELECT`). Those precomputed values are merged into the same `pool_entry` dict `generate_row()` already special-cases for overlap pools — `generate_row()` itself needs zero changes. `fakers.py` is split into `roll_field_seeds()` (the homogeneity-roll mechanism, called exactly once per field list, unchanged order/count from today) and a thin `fakers_from_seeds()`/`build_field_fakers()` layer on top, so the SQL path and the Python-Faker path share one roll instead of rolling independently.

**Tech Stack:** Python 3.14, DuckDB 1.5.3 (Python bindings), pytest, uv.

**Spec:** `docs/superpowers/specs/2026-09-01-duckdb-native-generation-design.md`

## Global Constraints

- No change to `generate_datasets`'s external signature/behavior, or to `GenerateRequest`/`GenerateResponse`.
- **This is NOT a zero-behavior-change migration.** SQL-generated values for the 5 v1 generators will differ from Faker's output for the same seed. Types, constraint bounds, null rates, and same-process/same-request determinism are preserved; exact values are not.
- A field only takes the SQL path if: its generator is in `SQL_GENERATOR_REGISTRY`, it has no `condition`, its generator is not `formula`/`shared_key`, and its name is not in the active request's `exact_fields`. Every field failing any check uses the existing, unmodified `generate_row()` Python path.
- `roll_field_seeds()` must be called exactly once per field list (parent fields once, child fields once, flat fields once) — never twice for the same list — to avoid double-rolling `random.randint`.
- Grouped datasets: parent-field values are generated **once per group** (plus once per ungrouped/"flat" row within a grouped dataset) — NOT once per output row. Get `parent_call_count` right (see Task 6) or parent SQL columns will run out of values or repeat wrong.
- Parameterize every SQL value with `?` — never string-interpolate constraint values, matching this codebase's existing SQL-safety convention (`validate_column_name`/`validate_table_name` for identifiers, `?` for values).
- All commands below run from `backend/` (i.e. `cd backend` first, once, for the session) — use the full absolute worktree path, this repo has both a shared main checkout and this isolated worktree at the same relative paths.

---

### Task 1: Extract `roll_field_seeds` in `fakers.py`

**Files:**
- Modify: `backend/app/services/generation_engine/fakers.py`
- Test: `backend/tests/test_generation.py` (existing suite must pass unmodified — this is a pure refactor)

**Interfaces:**
- Produces: `roll_field_seeds(fields, homogeneity, master_seed, namespace="") -> list[int | None]`, `fakers_from_seeds(seeds: list[int | None]) -> list[Faker | None]` — both used directly by Tasks 5/6.
- `build_field_fakers(fields, homogeneity, master_seed, namespace="") -> list[Faker | None]` keeps its exact existing signature/behavior (now a thin wrapper), used unchanged wherever it already is.

- [ ] **Step 1: Rewrite `fakers.py`**

```python
from __future__ import annotations

import random

from faker import Faker

from app.schemas.generation import FieldDefinition


def roll_field_seeds(
    fields: list[FieldDefinition],
    homogeneity: int,
    master_seed: int,
    namespace: str = "",
) -> list[int | None]:
    seeds: list[int | None] = []
    for field in fields:
        if field.generator in ("shared_key", "formula", "uuid4", "uuid_int"):
            seeds.append(None)
            continue
        seed_roll = random.randint(1, 100)
        use_master = seed_roll <= homogeneity
        if use_master:
            seeds.append((master_seed + hash(f"{namespace}{field.name}")) % (10**9))
        else:
            seeds.append(None)
    return seeds


def fakers_from_seeds(seeds: list[int | None]) -> list[Faker | None]:
    result: list[Faker | None] = []
    for seed in seeds:
        if seed is None:
            result.append(None)
        else:
            fk = Faker()
            fk.seed_instance(seed)
            result.append(fk)
    return result


def build_field_fakers(
    fields: list[FieldDefinition],
    homogeneity: int,
    master_seed: int,
    namespace: str = "",
) -> list[Faker | None]:
    return fakers_from_seeds(roll_field_seeds(fields, homogeneity, master_seed, namespace))
```

- [ ] **Step 2: Run the full backend suite to confirm zero regression**

Run: `uv run pytest tests/ -v`
Expected: all PASS, same 62/62 result as before this change — `build_field_fakers`'s output is unchanged by construction (it now calls the two new functions internally, but produces the identical `list[Faker | None]` for identical inputs).

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/generation_engine/fakers.py
git commit -m "refactor: extract roll_field_seeds/fakers_from_seeds from build_field_fakers"
```

---

### Task 2: `sql_generators.py` — SQL templates for the 5 v1 generators

**Files:**
- Create: `backend/app/services/generation_engine/sql_generators.py`
- Test: `backend/tests/test_sql_generators.py` (new)

**Interfaces:**
- Produces: `SQL_GENERATOR_REGISTRY: dict[str, Callable[[ConstraintConfig | None], tuple[str, list]]]` — each entry returns `(sql_expression_with_?_placeholders, param_values)`. Used by Task 4's `build_sql_columns`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_sql_generators.py
import uuid as uuid_mod

from app.core.database import DuckDBManager
from app.schemas.generation import ConstraintConfig, FieldDefinition
from app.services.generation_engine.sql_generators import SQL_GENERATOR_REGISTRY


def test_registry_has_v1_generators():
    assert set(SQL_GENERATOR_REGISTRY.keys()) == {
        "random_int", "pyint", "pydecimal", "boolean", "uuid4", "uuid_int",
    }


def test_random_int_expr_bounds():
    db = DuckDBManager.get_instance()
    expr, params = SQL_GENERATOR_REGISTRY["random_int"](ConstraintConfig(min=5, max=10))
    sql = f"SELECT {expr} FROM range(?)"
    rows = db.execute(sql, [*params, 200]).fetchall()
    values = [r[0] for r in rows]
    assert len(values) == 200
    assert all(isinstance(v, int) for v in values)
    assert all(5 <= v <= 10 for v in values)


def test_random_int_default_bounds():
    db = DuckDBManager.get_instance()
    expr, params = SQL_GENERATOR_REGISTRY["random_int"](None)
    sql = f"SELECT {expr} FROM range(?)"
    rows = db.execute(sql, [*params, 50]).fetchall()
    assert all(0 <= r[0] <= 999999 for r in rows)


def test_pydecimal_expr_bounds_and_rounding():
    db = DuckDBManager.get_instance()
    expr, params = SQL_GENERATOR_REGISTRY["pydecimal"](
        ConstraintConfig(min=0, max=100, right_digits=2)
    )
    sql = f"SELECT {expr} FROM range(?)"
    rows = db.execute(sql, [*params, 100]).fetchall()
    for (v,) in rows:
        assert 0 <= v <= 100
        assert round(v, 2) == v


def test_boolean_expr_type():
    db = DuckDBManager.get_instance()
    expr, params = SQL_GENERATOR_REGISTRY["boolean"](None)
    sql = f"SELECT {expr} FROM range(?)"
    rows = db.execute(sql, [*params, 50]).fetchall()
    assert all(isinstance(r[0], bool) for r in rows)


def test_uuid4_expr_format():
    db = DuckDBManager.get_instance()
    expr, params = SQL_GENERATOR_REGISTRY["uuid4"](None)
    sql = f"SELECT {expr} FROM range(?)"
    rows = db.execute(sql, [*params, 20]).fetchall()
    for (v,) in rows:
        uuid_mod.UUID(v)  # raises ValueError if malformed


def test_uuid_int_expr_range():
    db = DuckDBManager.get_instance()
    expr, params = SQL_GENERATOR_REGISTRY["uuid_int"](None)
    sql = f"SELECT {expr} FROM range(?)"
    rows = db.execute(sql, [*params, 50]).fetchall()
    for (v,) in rows:
        assert isinstance(v, int)
        assert 0 <= v < (1 << 63)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_sql_generators.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.generation_engine.sql_generators'`.

- [ ] **Step 3: Write `sql_generators.py`**

```python
from __future__ import annotations

from typing import Callable

from app.schemas.generation import ConstraintConfig


def _random_int_expr(cons: ConstraintConfig | None) -> tuple[str, list]:
    cmin = int(cons.min) if cons and cons.min is not None else 0
    cmax = int(cons.max) if cons and cons.max is not None else 999999
    return "CAST(FLOOR(random() * (? - ? + 1)) + ? AS BIGINT)", [cmax, cmin, cmin]


def _pydecimal_expr(cons: ConstraintConfig | None) -> tuple[str, list]:
    cmin = float(cons.min) if cons and cons.min is not None else 0.0
    cmax = float(cons.max) if cons and cons.max is not None else 999999.99
    right_digits = cons.right_digits if cons and cons.right_digits is not None else 2
    return "ROUND(? + random() * (? - ?), ?)", [cmin, cmax, cmin, right_digits]


def _boolean_expr(cons: ConstraintConfig | None) -> tuple[str, list]:
    return "(random() < 0.5)", []


def _uuid4_expr(cons: ConstraintConfig | None) -> tuple[str, list]:
    return "CAST(uuid() AS VARCHAR)", []


def _uuid_int_expr(cons: ConstraintConfig | None) -> tuple[str, list]:
    return "CAST(random() * 9223372036854775807 AS BIGINT)", []


SQL_GENERATOR_REGISTRY: dict[str, Callable[[ConstraintConfig | None], tuple[str, list]]] = {
    "random_int": _random_int_expr,
    "pyint": _random_int_expr,
    "pydecimal": _pydecimal_expr,
    "boolean": _boolean_expr,
    "uuid4": _uuid4_expr,
    "uuid_int": _uuid_int_expr,
}
```

Note: `random_int`'s `?` order in the SQL string is `(? - ? + 1)) + ?` = `(max - min + 1)) + min`, so `params = [cmax, cmin, cmin]` in that exact order. `pydecimal`'s is `? + random() * (? - ?)` = `min + random() * (max - min)`, so `params = [cmin, cmax, cmin]`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_sql_generators.py -v`
Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/generation_engine/sql_generators.py backend/tests/test_sql_generators.py
git commit -m "feat: add SQL_GENERATOR_REGISTRY for the 5 v1 DuckDB-native generators"
```

---

### Task 3: `is_sql_eligible`

**Files:**
- Modify: `backend/app/services/generation_engine/sql_generators.py`
- Test: `backend/tests/test_sql_generators.py`

**Interfaces:**
- Produces: `is_sql_eligible(field: FieldDefinition, exact_field_names: set[str]) -> bool` — used by Tasks 5/6.

- [ ] **Step 1: Write the failing tests**

```python
# append to backend/tests/test_sql_generators.py
from app.schemas.generation import FieldDefinition
from app.services.generation_engine.sql_generators import is_sql_eligible


def test_eligible_plain_field():
    field = FieldDefinition(name="n", generator="random_int", type="integer")
    assert is_sql_eligible(field, set()) is True


def test_ineligible_condition():
    field = FieldDefinition(name="n", generator="random_int", type="integer", condition="age >= 18")
    assert is_sql_eligible(field, set()) is False


def test_ineligible_exact_field():
    field = FieldDefinition(name="n", generator="random_int", type="integer")
    assert is_sql_eligible(field, {"n"}) is False


def test_ineligible_non_sql_generator():
    field = FieldDefinition(name="e", generator="email", type="string")
    assert is_sql_eligible(field, set()) is False


def test_ineligible_shared_key():
    field = FieldDefinition(name="sk", generator="shared_key", type="string")
    assert is_sql_eligible(field, set()) is False


def test_ineligible_formula():
    field = FieldDefinition(name="fm", generator="formula", type="string", formula="{{x}}")
    assert is_sql_eligible(field, set()) is False
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_sql_generators.py -v`
Expected: 6 new tests FAIL — `ImportError: cannot import name 'is_sql_eligible'`.

- [ ] **Step 3: Add `is_sql_eligible` to `sql_generators.py`**

Add this import and function to the top/bottom of the existing file:

```python
from app.schemas.generation import FieldDefinition  # add alongside the existing ConstraintConfig import


def is_sql_eligible(field: FieldDefinition, exact_field_names: set[str]) -> bool:
    return (
        field.generator in SQL_GENERATOR_REGISTRY
        and not field.condition
        and field.generator not in ("formula", "shared_key")
        and field.name not in exact_field_names
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_sql_generators.py -v`
Expected: 12 tests total PASS (6 from Task 2 + 6 new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/generation_engine/sql_generators.py backend/tests/test_sql_generators.py
git commit -m "feat: add is_sql_eligible field-eligibility rule"
```

---

### Task 4: `build_sql_columns`

**Files:**
- Modify: `backend/app/services/generation_engine/sql_generators.py`
- Test: `backend/tests/test_sql_generators.py`

**Interfaces:**
- Consumes: `SQL_GENERATOR_REGISTRY` (Task 2).
- Produces: `build_sql_columns(db, fields: list[FieldDefinition], rows: int, field_seeds: dict[str, int | None]) -> dict[str, list]` — used by Tasks 5/6.

- [ ] **Step 1: Write the failing tests**

```python
# append to backend/tests/test_sql_generators.py
from app.services.generation_engine.sql_generators import build_sql_columns


def test_build_sql_columns_returns_all_fields():
    db = DuckDBManager.get_instance()
    fields = [
        FieldDefinition(name="n", generator="random_int", type="integer",
                         constraint=ConstraintConfig(min=1, max=10)),
        FieldDefinition(name="ok", generator="boolean", type="boolean"),
    ]
    columns = build_sql_columns(db, fields, 30, {"n": None, "ok": None})
    assert set(columns.keys()) == {"n", "ok"}
    assert len(columns["n"]) == 30
    assert len(columns["ok"]) == 30
    assert all(1 <= v <= 10 for v in columns["n"])


def test_build_sql_columns_null_probability():
    db = DuckDBManager.get_instance()
    field = FieldDefinition(name="n", generator="random_int", type="integer",
                             constraint=ConstraintConfig(min=1, max=10), null_probability=1.0)
    columns = build_sql_columns(db, [field], 30, {"n": None})
    assert all(v is None for v in columns["n"])


def test_build_sql_columns_null_probability_partial():
    db = DuckDBManager.get_instance()
    field = FieldDefinition(name="n", generator="random_int", type="integer",
                             constraint=ConstraintConfig(min=1, max=10), null_probability=0.5)
    columns = build_sql_columns(db, [field], 500, {"n": None})
    none_count = sum(1 for v in columns["n"] if v is None)
    assert 150 < none_count < 350  # ~50% of 500, generous tolerance


def test_build_sql_columns_determinism_same_seed():
    db = DuckDBManager.get_instance()
    field = FieldDefinition(name="n", generator="random_int", type="integer",
                             constraint=ConstraintConfig(min=1, max=1000000))
    a = build_sql_columns(db, [field], 20, {"n": 12345})
    b = build_sql_columns(db, [field], 20, {"n": 12345})
    assert a == b


def test_build_sql_columns_different_seed_differs():
    db = DuckDBManager.get_instance()
    field = FieldDefinition(name="n", generator="random_int", type="integer",
                             constraint=ConstraintConfig(min=1, max=1000000))
    a = build_sql_columns(db, [field], 20, {"n": 111})
    b = build_sql_columns(db, [field], 20, {"n": 222})
    assert a != b
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_sql_generators.py -v`
Expected: 5 new tests FAIL — `ImportError: cannot import name 'build_sql_columns'`.

- [ ] **Step 3: Add `build_sql_columns` to `sql_generators.py`**

```python
def build_sql_columns(
    db,
    fields: list[FieldDefinition],
    rows: int,
    field_seeds: dict[str, int | None],
) -> dict[str, list]:
    columns: dict[str, list] = {}
    for field in fields:
        template_fn = SQL_GENERATOR_REGISTRY[field.generator]
        expr, params = template_fn(field.constraint)
        seed = field_seeds.get(field.name)
        if seed is not None:
            seed_float = (seed % 2_000_000) / 1_000_000 - 1.0
            db.execute("SELECT setseed(?)", [seed_float])
        if field.null_probability:
            sql = f"SELECT CASE WHEN random() < ? THEN NULL ELSE {expr} END FROM range(?)"
            full_params = [field.null_probability, *params, rows]
        else:
            sql = f"SELECT {expr} FROM range(?)"
            full_params = [*params, rows]
        result = db.execute(sql, full_params).fetchall()
        columns[field.name] = [r[0] for r in result]
    return columns
```

Note: `field_seeds.get(field.name)` will be `None` for every `uuid4`/`uuid_int` field, always — `roll_field_seeds` (Task 1) never assigns them a seed, matching their pre-existing, permanently-unseeded behavior in the Python path (`uuid.uuid4()` cannot be seeded). No special-casing needed here; this falls out of Task 1's existing skip-list.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_sql_generators.py -v`
Expected: 17 tests total PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/generation_engine/sql_generators.py backend/tests/test_sql_generators.py
git commit -m "feat: add build_sql_columns bulk generator"
```

---

### Task 5: Wire the SQL fast path into `flat.py`

**Files:**
- Modify: `backend/app/services/generation_engine/flat.py`
- Modify: `backend/app/services/generation_engine/engine.py` (thread `exact_field_names` through to `generate_dataset`)
- Test: `backend/tests/test_generation.py`

**Interfaces:**
- Consumes: `roll_field_seeds`/`fakers_from_seeds` (Task 1), `is_sql_eligible`/`build_sql_columns` (Tasks 3/4).
- Produces: `generate_dataset(..., exact_field_names: set[str] | None = None)` — new optional parameter, used by `engine.py`.

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_generation.py
def test_sql_eligible_field_in_flat_dataset(db):
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(
                name="flat_sql",
                rows=50,
                fields=[
                    FieldDefinition(name="id", generator="random_int", type="integer",
                                     constraint=ConstraintConfig(min=1, max=1000000)),
                    FieldDefinition(name="email", generator="email", type="string"),
                    FieldDefinition(name="active", generator="boolean", type="boolean"),
                ],
            ),
        ],
        homogeneity=100,
        seed=42,
    )
    resp = generate_datasets(req)
    table = resp.datasets[0].table_name
    rows = db.execute(f'SELECT id, email, active FROM "{table}"').fetchall()
    assert len(rows) == 50
    for row_id, email, active in rows:
        assert isinstance(row_id, int) and 1 <= row_id <= 1000000
        assert "@" in email
        assert isinstance(active, bool)


def test_sql_eligible_field_excluded_when_it_is_exact_field(db):
    # id is random_int (SQL-eligible by generator), but it's an exact_field for an
    # overlap request — it must still go through the Python/overlap-pool path.
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(name="a", rows=10, fields=[
                FieldDefinition(name="id", generator="random_int", type="integer",
                                 constraint=ConstraintConfig(min=1, max=1000000)),
            ]),
            DatasetDefinition(name="b", rows=10, fields=[
                FieldDefinition(name="id", generator="random_int", type="integer",
                                 constraint=ConstraintConfig(min=1, max=1000000)),
            ]),
        ],
        homogeneity=100,
        seed=1,
        overlap_ratio=1.0,
        exact_fields=["id"],
    )
    resp = generate_datasets(req)
    ids_a = [r[0] for r in db.execute(f'SELECT id FROM "{resp.datasets[0].table_name}"').fetchall()]
    ids_b = [r[0] for r in db.execute(f'SELECT id FROM "{resp.datasets[1].table_name}"').fetchall()]
    assert ids_a == ids_b  # overlap pool still works — id never took the SQL path
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_generation.py -v -k sql_eligible`
Expected: `test_sql_eligible_field_in_flat_dataset` likely PASSES already by coincidence (email/boolean still work via the old path, random_int just uses Faker) — but `test_sql_eligible_field_excluded_when_it_is_exact_field` should PASS too on the *old* code, since nothing SQL-related exists yet. Both should pass before this task's code change; that's expected — they're regression anchors, not red-green TDD for new code. Confirm both pass on current code before proceeding, so you know your baseline.

- [ ] **Step 3: Update `flat.py`**

```python
from __future__ import annotations

import logging
import uuid

from faker import Faker

from app.core.database import DuckDBManager
from app.core.validation import validate_column_name, validate_table_name
from app.schemas.generation import DatasetDefinition, DatasetResult
from app.services.generation_engine.fakers import fakers_from_seeds, roll_field_seeds
from app.services.generation_engine.persistence import (
    create_table,
    infer_duckdb_types,
    persist_dataset_metadata,
)
from app.services.generation_engine.row_builder import generate_row
from app.services.generation_engine.sql_generators import build_sql_columns, is_sql_eligible

logger = logging.getLogger(__name__)


def generate_dataset(
    fake: Faker,
    definition: DatasetDefinition,
    run_id: int,
    homogeneity: int,
    master_seed: int,
    overlap_pool: list[dict] | None = None,
    exact_field_names: set[str] | None = None,
) -> DatasetResult:
    fields = definition.fields
    rows = definition.rows
    dataset_id = str(uuid.uuid4())
    table_name = f"dataset_{dataset_id}"
    validate_table_name(table_name)

    column_names = [validate_column_name(f.name) for f in fields]
    col_types = infer_duckdb_types(fields)

    db = DuckDBManager.get_instance()
    create_table(db, table_name, column_names, col_types)

    shared_key_pool: list | None = None
    if definition.shared_key:
        sk_table = definition.shared_key.source_dataset
        validate_table_name(f"dataset_{sk_table}")
        sk_field = validate_column_name(definition.shared_key.source_field)
        try:
            result = db.execute(
                f'SELECT "{sk_field}" FROM "dataset_{sk_table}"'
            ).fetchall()
            shared_key_pool = [row[0] for row in result]
        except Exception:
            logger.exception("Failed to load shared_key pool")
            shared_key_pool = []

    exact_names = exact_field_names or set()
    seeds = roll_field_seeds(fields, homogeneity, master_seed)
    field_fakers = fakers_from_seeds(seeds)

    sql_fields = [f for f in fields if is_sql_eligible(f, exact_names)]
    if sql_fields:
        field_seeds_by_name = {f.name: seeds[i] for i, f in enumerate(fields)}
        sql_columns = build_sql_columns(db, sql_fields, rows, field_seeds_by_name)
    else:
        sql_columns = {}

    batch_size = 5000
    columns_formatted = ", ".join(f'"{c}"' for c in column_names)
    placeholders = ", ".join(["?"] * len(column_names))
    insert_sql = f'INSERT INTO "{table_name}" ({columns_formatted}) VALUES ({placeholders})'

    pool = overlap_pool or []

    for batch_start in range(0, rows, batch_size):
        batch_end = min(batch_start + batch_size, rows)
        batch_data: list[list] = []

        for row_idx in range(batch_start, batch_end):
            pool_entry = pool[row_idx] if row_idx < len(pool) else {}
            sql_entry = {name: values[row_idx] for name, values in sql_columns.items()}
            row = generate_row(
                fields,
                field_fakers,
                fake,
                pool_entry={**sql_entry, **pool_entry},
                shared_key_pool=shared_key_pool,
            )
            batch_data.append(row)

        db.executemany(insert_sql, batch_data)

    result = db.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()
    actual_count = result[0] if result else 0

    return persist_dataset_metadata(
        db, definition, dataset_id, table_name, run_id, homogeneity, master_seed, actual_count, column_names
    )
```

- [ ] **Step 4: Thread `exact_field_names` through `engine.py`**

In `backend/app/services/generation_engine/engine.py`, both call sites in `generate_datasets`'s dataset loop gain `exact_field_names=exact_field_names` (the variable is already computed earlier in the function via `exact_field_names = set(request.exact_fields)`):

```python
    dataset_results: list[DatasetResult] = []
    for dataset_def in request.datasets:
        if dataset_def.group_config:
            dr = generate_grouped_dataset(
                fake=main_fake,
                definition=dataset_def,
                run_id=run_id,
                homogeneity=request.homogeneity,
                master_seed=master_seed,
                overlap_pool=overlap_pool,
                exact_field_names=exact_field_names,
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
            )
        dataset_results.append(dr)
```

`generate_grouped_dataset` doesn't accept this parameter yet — that's Task 6. Adding it to this call site now is fine; Python allows passing a keyword argument the function doesn't yet declare only if the function accepts `**kwargs`, which it doesn't — **so this specific edit to the `generate_grouped_dataset(...)` call will break until Task 6 adds the parameter.** To keep this task's commit independently green, add the keyword only to the `generate_dataset(...)` (flat) call site in this task; add it to the `generate_grouped_dataset(...)` call site in Task 6 instead.

- [ ] **Step 5: Run the full suite to confirm no regression**

Run: `uv run pytest tests/ -v`
Expected: all PASS, including the 2 new tests from Step 1 and the full pre-existing suite (grouped-dataset tests untouched by this task).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/generation_engine/flat.py backend/app/services/generation_engine/engine.py backend/tests/test_generation.py
git commit -m "feat: wire DuckDB SQL fast path into flat dataset generation"
```

---

### Task 6: Wire the SQL fast path into `grouped.py`

**Files:**
- Modify: `backend/app/services/generation_engine/grouped.py`
- Modify: `backend/app/services/generation_engine/engine.py` (add the `exact_field_names` keyword to the grouped call site, deferred from Task 5)
- Test: `backend/tests/test_generation.py`

**Interfaces:**
- Consumes: same as Task 5, applied to `parent_fields` and `child_fields` independently (own namespace `"parent_"`/`"child_"`, matching the existing convention).
- Produces: `generate_grouped_dataset(..., exact_field_names: set[str] | None = None)`.

**The one non-obvious detail in this task:** parent-field values are generated **once per group**, not once per output row — and grouped datasets also generate independent "flat" (ungrouped) rows when `split_pct < 100`, each with its *own* one-off parent row (`parent_id=None`). So the total count of parent-row generations is `num_groups + flat_rows` when the grouped portion runs, or just `flat_rows` when it doesn't (`num_groups == 0` or `grouped_rows == 0`). `build_sql_columns` for parent fields must be sized to that count, not `total_rows`, and consumed via a running counter that increments on every parent-row generation (both inside the grouped loop and the flat-rows loop) — mirroring the existing `row_idx` counter pattern already used for child rows/overlap-pool lookups.

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_generation.py
def test_sql_eligible_fields_in_grouped_dataset(db):
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(
                name="grouped_sql",
                rows=30,
                group_config=GroupConfig(
                    num_groups=3,
                    split_pct=100,
                    parent_fields=[
                        FieldDefinition(name="trade_id", generator="uuid4", type="string"),
                        FieldDefinition(name="group_num", generator="random_int", type="integer",
                                         constraint=ConstraintConfig(min=1, max=100)),
                    ],
                    child_fields=[
                        FieldDefinition(name="qty", generator="random_int", type="integer",
                                         constraint=ConstraintConfig(min=1, max=1000)),
                        FieldDefinition(name="counterparty", generator="company", type="string"),
                    ],
                ),
            ),
        ],
        homogeneity=100,
        seed=7,
    )
    resp = generate_datasets(req)
    table = resp.datasets[0].table_name
    rows = db.execute(
        f'SELECT trade_id, group_num, qty, counterparty, parent_id FROM "{table}"'
    ).fetchall()
    assert len(rows) == 30
    for trade_id, group_num, qty, counterparty, parent_id in rows:
        assert 1 <= group_num <= 100
        assert 1 <= qty <= 1000
        assert counterparty  # non-empty Faker company name, unaffected by this migration
        assert parent_id is not None

    # Each distinct trade_id (an SQL-generated PARENT field) must map to exactly one
    # parent_id — proving the parent-row-per-group counting is correct, not reused
    # across groups or regenerated per child row.
    groups_seen: dict[str, set] = {}
    for trade_id, _, _, _, parent_id in rows:
        groups_seen.setdefault(trade_id, set()).add(parent_id)
    assert all(len(pids) == 1 for pids in groups_seen.values())
    assert len(groups_seen) == 3  # exactly 3 distinct parent trade_ids for 3 groups


def test_sql_eligible_fields_in_grouped_dataset_with_flat_rows(db):
    # split_pct < 100 means some rows are "flat" (ungrouped, parent_id=None), each
    # generating its own one-off parent row — this exercises the flat_rows branch
    # of the parent_call_count logic, not just the grouped branch.
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(
                name="grouped_sql_partial",
                rows=20,
                group_config=GroupConfig(
                    num_groups=2,
                    split_pct=50,
                    parent_fields=[
                        FieldDefinition(name="group_num", generator="random_int", type="integer",
                                         constraint=ConstraintConfig(min=1, max=100)),
                    ],
                    child_fields=[
                        FieldDefinition(name="qty", generator="random_int", type="integer",
                                         constraint=ConstraintConfig(min=1, max=1000)),
                    ],
                ),
            ),
        ],
        homogeneity=100,
        seed=9,
    )
    resp = generate_datasets(req)
    table = resp.datasets[0].table_name
    rows = db.execute(f'SELECT group_num, qty, parent_id FROM "{table}"').fetchall()
    assert len(rows) == 20
    flat_rows = [r for r in rows if r[2] is None]
    grouped_rows = [r for r in rows if r[2] is not None]
    assert len(flat_rows) == 10  # 50% of 20
    assert len(grouped_rows) == 10
    for group_num, qty, _ in rows:
        assert 1 <= group_num <= 100
        assert 1 <= qty <= 1000
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_generation.py -v -k grouped_sql`
Expected: FAIL — `generate_grouped_dataset` doesn't accept/use SQL fields yet, so `group_num`'s value would currently come from Faker's `random_int` (still numerically valid, so this might not actually fail on assertions — but Task 5's engine.py edit already broke the grouped call site per Task 5 Step 4's note, so this WILL fail with a `TypeError: generate_grouped_dataset() got an unexpected keyword argument 'exact_field_names'` until this task adds the parameter). Confirm that's the actual failure before proceeding.

- [ ] **Step 3: Update `grouped.py`**

```python
from __future__ import annotations

import random
import uuid

from faker import Faker

from app.core.database import DuckDBManager
from app.core.validation import validate_column_name, validate_table_name
from app.schemas.generation import DatasetDefinition, DatasetResult
from app.services.generation_engine.fakers import fakers_from_seeds, roll_field_seeds
from app.services.generation_engine.persistence import (
    create_table,
    infer_duckdb_types,
    persist_dataset_metadata,
)
from app.services.generation_engine.row_builder import generate_row
from app.services.generation_engine.sql_generators import build_sql_columns, is_sql_eligible


def generate_grouped_dataset(
    fake: Faker,
    definition: DatasetDefinition,
    run_id: int,
    homogeneity: int,
    master_seed: int,
    overlap_pool: list[dict] | None = None,
    exact_field_names: set[str] | None = None,
) -> DatasetResult:
    group_cfg = definition.group_config
    assert group_cfg is not None

    total_rows = definition.rows
    num_groups = group_cfg.num_groups
    split_pct = group_cfg.split_pct
    parent_fields = group_cfg.parent_fields
    child_fields = group_cfg.child_fields

    grouped_rows = int(total_rows * split_pct / 100)
    flat_rows = total_rows - grouped_rows
    grouped_enabled = num_groups > 0 and grouped_rows > 0

    dataset_id = str(uuid.uuid4())
    table_name = f"dataset_{dataset_id}"
    validate_table_name(table_name)

    all_fields = parent_fields + child_fields
    column_names = [validate_column_name(f.name) for f in all_fields]
    column_names.append("parent_id")
    col_types = infer_duckdb_types(all_fields) + ["VARCHAR"]

    db = DuckDBManager.get_instance()
    create_table(db, table_name, column_names, col_types)

    exact_names = exact_field_names or set()

    parent_seeds = roll_field_seeds(parent_fields, homogeneity, master_seed, namespace="parent_")
    parent_fakers = fakers_from_seeds(parent_seeds)
    child_seeds = roll_field_seeds(child_fields, homogeneity, master_seed, namespace="child_")
    child_fakers = fakers_from_seeds(child_seeds)

    parent_call_count = (num_groups if grouped_enabled else 0) + flat_rows
    sql_parent_fields = [f for f in parent_fields if is_sql_eligible(f, exact_names)]
    if sql_parent_fields:
        parent_seeds_by_name = {f.name: parent_seeds[i] for i, f in enumerate(parent_fields)}
        sql_parent_columns = build_sql_columns(db, sql_parent_fields, parent_call_count, parent_seeds_by_name)
    else:
        sql_parent_columns = {}

    sql_child_fields = [f for f in child_fields if is_sql_eligible(f, exact_names)]
    if sql_child_fields:
        child_seeds_by_name = {f.name: child_seeds[i] for i, f in enumerate(child_fields)}
        sql_child_columns = build_sql_columns(db, sql_child_fields, total_rows, child_seeds_by_name)
    else:
        sql_child_columns = {}

    batch_size = 5000
    columns_formatted = ", ".join(f'"{c}"' for c in column_names)
    placeholders = ", ".join(["?"] * len(column_names))
    insert_sql = f'INSERT INTO "{table_name}" ({columns_formatted}) VALUES ({placeholders})'

    batch_data: list[list] = []
    pool = overlap_pool or []
    row_idx = 0
    parent_call_idx = 0

    def _next_parent_row() -> list:
        nonlocal parent_call_idx
        sql_entry = {name: values[parent_call_idx] for name, values in sql_parent_columns.items()}
        parent_row = generate_row(parent_fields, parent_fakers, fake, pool_entry=sql_entry)
        parent_call_idx += 1
        return parent_row

    # Distribute grouped_rows randomly across num_groups
    if grouped_enabled:
        raw_weights = [random.random() for _ in range(num_groups)]
        total_weight = sum(raw_weights)
        group_sizes = [max(1, int(grouped_rows * w / total_weight)) for w in raw_weights]
        diff = grouped_rows - sum(group_sizes)
        for i in range(abs(diff)):
            group_sizes[i % num_groups] += 1 if diff > 0 else -1
        group_sizes = [max(1, s) for s in group_sizes]

        for g_idx in range(num_groups):
            parent_id = str(uuid.uuid4())
            parent_row = _next_parent_row()

            child_count = group_sizes[g_idx]
            for _ in range(child_count):
                pool_entry = pool[row_idx] if row_idx < len(pool) else {}
                sql_entry = {name: values[row_idx] for name, values in sql_child_columns.items()}
                row_idx += 1
                child_row = generate_row(
                    child_fields, child_fakers, fake, pool_entry={**sql_entry, **pool_entry}
                )
                batch_data.append(parent_row + child_row + [parent_id])

                if len(batch_data) >= batch_size:
                    db.executemany(insert_sql, batch_data)
                    batch_data = []

    # Flat rows
    for _ in range(flat_rows):
        parent_row = _next_parent_row()
        pool_entry = pool[row_idx] if row_idx < len(pool) else {}
        sql_entry = {name: values[row_idx] for name, values in sql_child_columns.items()}
        row_idx += 1
        child_row = generate_row(
            child_fields, child_fakers, fake, pool_entry={**sql_entry, **pool_entry}
        )
        batch_data.append(parent_row + child_row + [None])

        if len(batch_data) >= batch_size:
            db.executemany(insert_sql, batch_data)
            batch_data = []

    if batch_data:
        db.executemany(insert_sql, batch_data)

    result = db.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()
    actual_count = result[0] if result else 0

    return persist_dataset_metadata(
        db, definition, dataset_id, table_name, run_id, homogeneity, master_seed, actual_count, column_names
    )
```

- [ ] **Step 4: Verify `engine.py` already has the keyword on the grouped call site**

This should already be present from Task 5 Step 4's edit (both call sites were shown together there, but only the flat one was meant to be applied in Task 5). Check `backend/app/services/generation_engine/engine.py` — if the `generate_grouped_dataset(...)` call is still missing `exact_field_names=exact_field_names`, add it now.

- [ ] **Step 5: Run the full suite to confirm no regression**

Run: `uv run pytest tests/ -v`
Expected: all PASS, including the 2 new tests from Step 1.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/generation_engine/grouped.py backend/app/services/generation_engine/engine.py backend/tests/test_generation.py
git commit -m "feat: wire DuckDB SQL fast path into grouped dataset generation"
```

---

### Task 7: Cross-boundary integration test — SQL field referenced by a Python `condition`

**Files:**
- Test: `backend/tests/test_generation.py`

**Interfaces:**
- None new — this task is pure test coverage for the riskiest interaction the eligibility rule creates: a field that stays on the Python path (because it has a `condition`) referencing an *earlier* field that took the SQL fast path.

**Why this needs its own task:** `check_condition` reads `row[field_indices[field_name]]` from the row list built so far in `generate_row`. For an SQL-eligible field, that row slot is filled via the `pool_entry` short-circuit (`row.append(pool_entry[field.name])`), not live generation — this test proves a later Python-path field's `condition` correctly sees that pool-injected value, exercising the exact mechanism Tasks 5/6 rely on but that none of their own tests directly targeted (they tested the SQL fields' own output, not a downstream field's *dependency* on one).

- [ ] **Step 1: Write the test**

```python
# append to backend/tests/test_generation.py
def test_condition_on_later_field_sees_sql_generated_earlier_field(db):
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(
                name="condition_on_sql_field",
                rows=200,
                fields=[
                    FieldDefinition(name="score", generator="random_int", type="integer",
                                     constraint=ConstraintConfig(min=1, max=100)),
                    FieldDefinition(name="tier", generator="random_element", type="string",
                                     constraint=ConstraintConfig(values="gold,standard"),
                                     condition="score >= 50"),
                ],
            ),
        ],
        homogeneity=100,
        seed=123,
    )
    resp = generate_datasets(req)
    table = resp.datasets[0].table_name
    rows = db.execute(f'SELECT score, tier FROM "{table}"').fetchall()
    assert len(rows) == 200
    saw_gold_or_standard = False
    saw_null_tier = False
    for score, tier in rows:
        assert 1 <= score <= 100  # score took the SQL path
        if score >= 50:
            assert tier in ("gold", "standard")
            saw_gold_or_standard = True
        else:
            assert tier is None  # condition correctly saw the SQL-generated score and skipped tier
            saw_null_tier = True
    # With 200 rows and a uniform [1,100] score, both branches should appear —
    # if this ever flakes, the seed/range no longer guarantees both branches occur.
    assert saw_gold_or_standard
    assert saw_null_tier
```

- [ ] **Step 2: Run to verify it passes**

Run: `uv run pytest tests/test_generation.py -v -k condition_on_sql_field`
Expected: PASS. If it fails, do not adjust the test to hide the failure — this is exactly the integration point most likely to expose a real bug in the `pool_entry` merge or `is_sql_eligible`'s exclusions; investigate the actual `generate_row`/`build_sql_columns`/eligibility interaction before touching the test.

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_generation.py
git commit -m "test: verify condition on a Python-path field sees an SQL-generated earlier field"
```

---

### Task 8: Final verification

**Files:**
- None (verification only).

- [ ] **Step 1: Run the full backend suite**

Run: `uv run pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 2: Confirm no unrelated files changed**

Run: `git diff --stat 4335b37..HEAD -- . ':!backend/app/services/generation_engine' ':!backend/tests'`
Expected: empty output — every change in this plan's commits is confined to `backend/app/services/generation_engine/` and `backend/tests/`.

- [ ] **Step 3: Confirm `generate_datasets`'s external contract is untouched**

Run: `cd backend && uv run python -c "from app.services.generation_engine import generate_datasets; from app.services import generation_engine; print(generation_engine.generate_datasets is generate_datasets)"`
Expected: `True`.

- [ ] **Step 4: Spot-check performance directionally (not a formal benchmark)**

Run:
```bash
uv run python -c "
import time
from app.schemas.generation import GenerateRequest, DatasetDefinition, FieldDefinition, ConstraintConfig
from app.services.generation_engine import generate_datasets

req = GenerateRequest(
    datasets=[DatasetDefinition(name='perf', rows=50000, fields=[
        FieldDefinition(name='id', generator='random_int', type='integer', constraint=ConstraintConfig(min=1, max=1000000)),
        FieldDefinition(name='score', generator='pydecimal', type='float', constraint=ConstraintConfig(min=0, max=100, right_digits=2)),
        FieldDefinition(name='active', generator='boolean', type='boolean'),
        FieldDefinition(name='uid', generator='uuid4', type='string'),
    ])],
    homogeneity=50, seed=1,
)
start = time.perf_counter()
resp = generate_datasets(req)
print(f'50K rows, 4 all-SQL-eligible fields: {time.perf_counter() - start:.2f}s')
"
```
Expected: notably faster than MIGRATION.md's baseline figure (~3-5s for 100K rows × 15 fields, i.e. roughly proportional to ~0.75-1.25s for 50K rows × 4 fields under the old all-Python path). This step is a sanity check that the migration is actually delivering the intended win, not a pass/fail gate — record the number in the final report; a formal benchmark comparison is out of scope for this plan.

- [ ] **Step 5: Commit** (only if Steps 1–4 surfaced any fix-up changes; otherwise this task is verification-only)
