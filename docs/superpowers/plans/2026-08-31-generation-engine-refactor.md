# Generation Engine Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `backend/app/services/generation_engine.py` (591 lines) into a `generation_engine/` package of focused modules, eliminating the duplication between flat and grouped dataset generation, with zero behavior or API change.

**Architecture:** Bottom-up extraction. Task 1 moves the file into a package unchanged (pure rename, establishes the safety baseline). Tasks 2–6 pull independent leaf pieces (generators, conditions, fakers, overlap, persistence) out of the monolith one at a time. Task 7 unifies the two duplicate row-generation implementations into one shared `row_builder.py`. Task 8 splits what remains into `flat.py`/`grouped.py`/`engine.py`. Every task ends by running the full backend test suite — this is the regression contract, since `test_generation.py` already covers flat/grouped/overlap/grouped-overlap end-to-end and its import (`from app.services.generation_engine import generate_datasets`) never changes.

**Tech Stack:** Python 3.14, FastAPI, DuckDB, Faker, Jinja2, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-08-31-generation-engine-refactor-design.md`

## Global Constraints

- No change to `generate_datasets`' signature, behavior, or the `GenerateRequest`/`GenerateResponse` schemas.
- No change to what's supported — grouped datasets still don't support `shared_key` fields (a pre-existing quirk, not a bug to fix here).
- `random.*` calls must happen in the exact same order and count as today, per field, per row — seeded tests (`homogeneity=100`, fixed `seed=`) assert exact output and will fail if draw order shifts.
- Every existing import of the module (`from app.services.generation_engine import generate_datasets`, `from app.services import generation_engine`) must keep working unchanged — used by `app/routers/generation.py`, `backend/tui/screens/generation.py`, `backend/cli/generate.py`, and `backend/tests/{test_generation,test_api,test_export,test_transform}.py`.
- All commands below run from `backend/` (i.e. `cd backend` first, once, for the session).

---

### Task 1: Convert `generation_engine.py` to a package (pure move)

**Files:**
- Create: `backend/app/services/generation_engine/__init__.py`
- Create: `backend/app/services/generation_engine/engine.py` (full content of today's `generation_engine.py`, unchanged)
- Delete: `backend/app/services/generation_engine.py`

**Interfaces:**
- Produces: `generation_engine.generate_datasets(request: GenerateRequest) -> GenerateResponse` — identical to today, now re-exported from the package `__init__.py`.

- [ ] **Step 1: Run the full backend suite to record the baseline**

Run: `uv run pytest tests/ -v`
Expected: all tests PASS (this is today's behavior — record it before touching anything).

- [ ] **Step 2: Move the file into a package, content unchanged**

```bash
mkdir -p backend/app/services/generation_engine
git mv backend/app/services/generation_engine.py backend/app/services/generation_engine/engine.py
```

- [ ] **Step 3: Create the package `__init__.py`**

```python
from app.services.generation_engine.engine import generate_datasets

__all__ = ["generate_datasets"]
```

- [ ] **Step 4: Run the full suite again to confirm the pure move didn't break anything**

Run: `uv run pytest tests/ -v`
Expected: same PASS result as Step 1 — identical test count, identical outcomes.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/generation_engine
git commit -m "refactor: convert generation_engine.py to a package"
```

---

### Task 2: Extract `generators.py`

**Files:**
- Create: `backend/app/services/generation_engine/generators.py`
- Modify: `backend/app/services/generation_engine/engine.py` (remove `_apply_constraint`, `_generate_field_value`; import from `generators.py` instead)
- Test: `backend/tests/test_generators.py` (new)

**Interfaces:**
- Consumes: `app.schemas.generation.{ConstraintConfig, FieldDefinition}` (unchanged schemas).
- Produces: `apply_constraint(fake, value, constraint) -> object`, `generate_field_value(fake, field, constraint) -> object`, `GENERATOR_REGISTRY: dict[str, Callable]` — used by `overlap.py` (Task 5) and `row_builder.py` (Task 7).

- [ ] **Step 1: Create `generators.py`**

```python
from __future__ import annotations

import logging
import random
import uuid
from typing import Callable

from faker import Faker

from app.schemas.generation import ConstraintConfig, FieldDefinition

logger = logging.getLogger(__name__)


def apply_constraint(fake: Faker, value: object, constraint: ConstraintConfig | None) -> object:
    if constraint is None:
        return value
    if isinstance(value, (int, float)):
        cmin = constraint.min if constraint.min is not None else float("-inf")
        cmax = constraint.max if constraint.max is not None else float("inf")
        if isinstance(value, float) and constraint.right_digits is not None:
            value = round(value, constraint.right_digits)
        return max(cmin, min(cmax, value))
    return value


def _random_element(fake: Faker, cons: ConstraintConfig | None) -> object:
    if cons and cons.values:
        vals = [v.strip() for v in cons.values.split(",")]
        if cons.weights:
            weights = [float(w.strip()) for w in cons.weights.split(",")]
            return random.choices(vals, weights=weights, k=1)[0]
        return fake.random_element(vals)
    return fake.word()


GENERATOR_REGISTRY: dict[str, Callable[[Faker, ConstraintConfig | None], object]] = {
    "first_name": lambda fake, cons: fake.first_name(),
    "last_name": lambda fake, cons: fake.last_name(),
    "name": lambda fake, cons: fake.name(),
    "email": lambda fake, cons: fake.email(),
    "phone_number": lambda fake, cons: fake.phone_number(),
    "job": lambda fake, cons: fake.job(),
    "company": lambda fake, cons: fake.company(),
    "company_suffix": lambda fake, cons: fake.company_suffix(),
    "catch_phrase": lambda fake, cons: fake.catch_phrase(),
    "domain_name": lambda fake, cons: fake.domain_name(),
    "url": lambda fake, cons: fake.url(),
    "country": lambda fake, cons: fake.country(),
    "country_code": lambda fake, cons: fake.country_code(),
    "city": lambda fake, cons: fake.city(),
    "street_address": lambda fake, cons: fake.street_address(),
    "zipcode": lambda fake, cons: fake.zipcode(),
    "text": lambda fake, cons: fake.text(max_nb_chars=int(cons.max) if cons and cons.max else 100),
    "boolean": lambda fake, cons: fake.boolean(),
    "random_int": lambda fake, cons: fake.random_int(
        min=int(cons.min) if cons and cons.min is not None else 0,
        max=int(cons.max) if cons and cons.max is not None else 999999,
    ),
    "pyint": lambda fake, cons: fake.random_int(
        min=int(cons.min) if cons and cons.min is not None else 0,
        max=int(cons.max) if cons and cons.max is not None else 999999,
    ),
    "pydecimal": lambda fake, cons: float(
        fake.pydecimal(
            min_value=float(cons.min) if cons and cons.min is not None else 0.0,
            max_value=float(cons.max) if cons and cons.max is not None else 999999.99,
            right_digits=cons.right_digits if cons and cons.right_digits is not None else 2,
        )
    ),
    "bothify": lambda fake, cons: fake.bothify(text=cons.format if cons and cons.format else "?????#####"),
    "random_element": _random_element,
    "currency_code": lambda fake, cons: fake.currency_code(),
    "swift": lambda fake, cons: fake.swift8(),
    "iban": lambda fake, cons: fake.iban(),
    "bban": lambda fake, cons: fake.bban(),
    "date_between": lambda fake, cons: fake.date_between(
        start_date=cons.start if cons and cons.start else "-5y",
        end_date=cons.end if cons and cons.end else "today",
    ).isoformat(),
    "date_of_birth": lambda fake, cons: fake.date_of_birth(
        minimum_age=cons.min_age if cons and cons.min_age is not None else 18,
        maximum_age=cons.max_age if cons and cons.max_age is not None else 99,
    ).isoformat(),
    "date_time": lambda fake, cons: fake.date_time().isoformat(),
    "word": lambda fake, cons: fake.word(),
}


def generate_field_value(fake: Faker, field: FieldDefinition, constraint: ConstraintConfig | None) -> object:
    gen = field.generator
    cons = constraint or field.constraint

    if gen == "uuid4":
        return str(uuid.uuid4())
    if gen == "uuid_int":
        return uuid.uuid4().int & ((1 << 63) - 1)
    if gen == "formula":
        return apply_constraint(fake, field.formula or "", cons)
    if gen == "shared_key":
        return apply_constraint(fake, "", cons)

    handler = GENERATOR_REGISTRY.get(gen)
    if handler is None:
        logger.warning("Unknown generator '%s' for field '%s', falling back to fake.word()", gen, field.name)
        return apply_constraint(fake, fake.word(), cons)
    return apply_constraint(fake, handler(fake, cons), cons)
```

Note: `uuid4`/`uuid_int`/`formula`/`shared_key` are handled before the registry lookup, matching today's if/elif order exactly — `uuid4`/`uuid_int` never go through `apply_constraint`'s min/max clamp (same as today), `formula`/`shared_key` do.

- [ ] **Step 2: Remove `_apply_constraint` and `_generate_field_value` from `engine.py`, import from `generators.py`**

In `backend/app/services/generation_engine/engine.py`:
- Delete the `_apply_constraint` function body (originally lines 70–79).
- Delete the `_generate_field_value` function body (originally lines 82–175).
- Add to the imports: `from app.services.generation_engine.generators import apply_constraint, generate_field_value`.
- Replace every call site `_apply_constraint(...)` → `apply_constraint(...)` and `_generate_field_value(...)` → `generate_field_value(...)` in the remaining code (the row-generation loops and `_build_overlap_pool`).

- [ ] **Step 3: Run the full suite to confirm no regression**

Run: `uv run pytest tests/ -v`
Expected: all PASS, same as Task 1's baseline.

- [ ] **Step 4: Add a unit test locking in the extraction boundary**

```python
# backend/tests/test_generators.py
from app.schemas.generation import ConstraintConfig, FieldDefinition
from app.services.generation_engine.generators import GENERATOR_REGISTRY, generate_field_value
from faker import Faker


def test_registry_dispatch_for_email():
    fake = Faker()
    fake.seed_instance(1)
    field = FieldDefinition(name="e", generator="email", type="string")
    value = generate_field_value(fake, field, None)
    assert "@" in value


def test_unknown_generator_falls_back_to_word(caplog):
    fake = Faker()
    fake.seed_instance(1)
    field = FieldDefinition(name="mystery", generator="not_a_real_generator", type="string")
    with caplog.at_level("WARNING"):
        value = generate_field_value(fake, field, None)
    assert isinstance(value, str)
    assert "not_a_real_generator" not in GENERATOR_REGISTRY
    assert "Unknown generator" in caplog.text


def test_random_element_respects_weights():
    fake = Faker()
    field = FieldDefinition(name="status", generator="random_element", type="string")
    cons = ConstraintConfig(values="a,b", weights="100,0")
    results = {generate_field_value(fake, field, cons) for _ in range(20)}
    assert results == {"a"}
```

- [ ] **Step 5: Run the new test file to verify it passes**

Run: `uv run pytest tests/test_generators.py -v`
Expected: 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/generation_engine backend/tests/test_generators.py
git commit -m "refactor: extract generator registry into generators.py"
```

---

### Task 3: Extract `conditions.py`

**Files:**
- Create: `backend/app/services/generation_engine/conditions.py`
- Modify: `backend/app/services/generation_engine/engine.py` (remove `_check_condition`; import `check_condition`)
- Test: `backend/tests/test_conditions.py` (new)

**Interfaces:**
- Produces: `check_condition(condition: str, row: list, fields: list) -> bool` — used by `row_builder.py` (Task 7).

- [ ] **Step 1: Create `conditions.py`** (exact copy of today's `_check_condition`, renamed)

```python
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def check_condition(condition: str, row: list, fields: list) -> bool:
    if not condition:
        return True
    m = re.match(r'^\s*(\w+)\s*(>=|<=|!=|==|>|<)\s*(.+)\s*$', condition)
    if not m:
        return True
    field_name, op, raw_val = m.group(1), m.group(2), m.group(3).strip()

    field_indices = {f.name: i for i, f in enumerate(fields)}
    if field_name not in field_indices:
        return True

    field_val = row[field_indices[field_name]]
    if field_val is None:
        return False

    try:
        val = int(raw_val) if raw_val.isdigit() else (float(raw_val) if '.' in raw_val else raw_val.strip('"').strip("'"))
    except ValueError:
        val = raw_val.strip('"').strip("'")

    try:
        if op == ">=":
            return field_val >= val
        elif op == "<=":
            return field_val <= val
        elif op == ">":
            return field_val > val
        elif op == "<":
            return field_val < val
        elif op == "==":
            return field_val == val
        elif op == "!=":
            return field_val != val
        return True
    except TypeError:
        logger.warning("Type mismatch in condition '%s': %s vs %s", condition, type(field_val).__name__, type(val).__name__)
        return False
```

- [ ] **Step 2: Remove `_check_condition` from `engine.py`, import `check_condition`**

Delete the `_check_condition` function (originally lines 30–67). Add `from app.services.generation_engine.conditions import check_condition` to the imports. Replace `_check_condition(...)` call sites with `check_condition(...)`.

- [ ] **Step 3: Run the full suite to confirm no regression**

Run: `uv run pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 4: Add unit tests for `check_condition`**

```python
# backend/tests/test_conditions.py
from app.schemas.generation import FieldDefinition
from app.services.generation_engine.conditions import check_condition


def _fields():
    return [FieldDefinition(name="age", generator="random_int", type="integer")]


def test_condition_true_when_satisfied():
    assert check_condition("age >= 18", [21], _fields()) is True


def test_condition_false_when_not_satisfied():
    assert check_condition("age >= 18", [10], _fields()) is False


def test_condition_not_equal():
    assert check_condition("age != 10", [21], _fields()) is True
    assert check_condition("age != 10", [10], _fields()) is False


def test_condition_none_value_is_false():
    assert check_condition("age >= 18", [None], _fields()) is False


def test_unrecognized_condition_string_defaults_true():
    assert check_condition("not a real condition", [21], _fields()) is True


def test_empty_condition_defaults_true():
    assert check_condition("", [21], _fields()) is True
```

- [ ] **Step 5: Run the new test file to verify it passes**

Run: `uv run pytest tests/test_conditions.py -v`
Expected: 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/generation_engine backend/tests/test_conditions.py
git commit -m "refactor: extract check_condition into conditions.py"
```

---

### Task 4: Extract `fakers.py` (deduplicate the 3× homogeneity-seeding loop)

**Files:**
- Create: `backend/app/services/generation_engine/fakers.py`
- Modify: `backend/app/services/generation_engine/engine.py` (replace the flat field-faker loop and the parent/child field-faker loops with calls to `build_field_fakers`)

**Interfaces:**
- Consumes: `app.schemas.generation.FieldDefinition`.
- Produces: `build_field_fakers(fields: list[FieldDefinition], homogeneity: int, master_seed: int, namespace: str = "") -> list[Faker | None]` — used by `flat.py` and `grouped.py` (Task 8).

- [ ] **Step 1: Create `fakers.py`**

```python
from __future__ import annotations

import random

from faker import Faker

from app.schemas.generation import FieldDefinition


def build_field_fakers(
    fields: list[FieldDefinition],
    homogeneity: int,
    master_seed: int,
    namespace: str = "",
) -> list[Faker | None]:
    result: list[Faker | None] = []
    for field in fields:
        if field.generator in ("shared_key", "formula", "uuid4", "uuid_int"):
            result.append(None)
            continue
        seed_roll = random.randint(1, 100)
        use_master = seed_roll <= homogeneity
        if use_master:
            field_seed = (master_seed + hash(f"{namespace}{field.name}")) % (10**9)
            fk = Faker()
            fk.seed_instance(field_seed)
            result.append(fk)
        else:
            result.append(None)
    return result
```

`namespace=""` reproduces today's flat-path `hash(field.name)` exactly (an empty prefix is a no-op on the f-string). `namespace="parent_"` and `namespace="child_"` reproduce today's grouped-path `hash(f"parent_{field.name}")` / `hash(f"child_{field.name}")` exactly. The `field_uses_master` list that today's flat loop builds is dropped here — it's computed but never read anywhere else in the original file (verify with `grep -n field_uses_master backend/app/services/generation_engine/engine.py` before this step — it should only appear in the loop that builds it).

- [ ] **Step 2: Replace the 3 duplicated loops in `engine.py` with calls to `build_field_fakers`**

In the flat generation function, replace the `field_fakers`/`field_uses_master` build loop with:
```python
field_fakers = build_field_fakers(fields, homogeneity, master_seed)
```
In the grouped generation function, replace the `parent_fakers` build loop with:
```python
parent_fakers = build_field_fakers(parent_fields, homogeneity, master_seed, namespace="parent_")
```
and the `child_fakers` build loop with:
```python
child_fakers = build_field_fakers(child_fields, homogeneity, master_seed, namespace="child_")
```
Add `from app.services.generation_engine.fakers import build_field_fakers` to the imports.

- [ ] **Step 3: Run the full suite — this is the critical RNG-order check**

Run: `uv run pytest tests/ -v`
Expected: all PASS, including every seeded/deterministic assertion in `test_generation.py`. If any seeded test fails here, the draw order or count changed — check the `namespace` values and the field-iteration order before anything else.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/generation_engine
git commit -m "refactor: extract build_field_fakers into fakers.py"
```

---

### Task 5: Extract `overlap.py`

**Files:**
- Create: `backend/app/services/generation_engine/overlap.py`
- Modify: `backend/app/services/generation_engine/engine.py` (remove `_effective_fields`, `_build_overlap_pool`; import `effective_fields`, `build_overlap_pool`)

**Interfaces:**
- Consumes: `generate_field_value` from `generators.py` (Task 2).
- Produces: `effective_fields(ds: DatasetDefinition) -> list[FieldDefinition]`, `build_overlap_pool(fake, fields, exact_field_names, pool_size) -> list[dict]` — used by `engine.py`'s `generate_datasets`.

- [ ] **Step 1: Create `overlap.py`**

```python
from __future__ import annotations

from faker import Faker

from app.schemas.generation import DatasetDefinition, FieldDefinition
from app.services.generation_engine.generators import generate_field_value


def effective_fields(ds: DatasetDefinition) -> list[FieldDefinition]:
    if ds.group_config:
        return ds.group_config.parent_fields + ds.group_config.child_fields
    return ds.fields


def build_overlap_pool(
    fake: Faker,
    fields: list[FieldDefinition],
    exact_field_names: set[str],
    pool_size: int,
) -> list[dict]:
    exact_fields = [f for f in fields if f.name in exact_field_names]
    pool = []
    for _ in range(pool_size):
        entry = {}
        for field in exact_fields:
            entry[field.name] = generate_field_value(fake, field, None)
        pool.append(entry)
    return pool
```

- [ ] **Step 2: Remove `_effective_fields` and `_build_overlap_pool` from `engine.py`, import the new names**

Delete both functions from `engine.py`. Add `from app.services.generation_engine.overlap import build_overlap_pool, effective_fields` to the imports. Replace the two call sites in `generate_datasets` (`_effective_fields(...)` → `effective_fields(...)`, `_build_overlap_pool(...)` → `build_overlap_pool(...)`).

- [ ] **Step 3: Run the full suite to confirm no regression**

Run: `uv run pytest tests/ -v`
Expected: all PASS, including `test_overlap_pool_built_from_first_grouped_dataset` and the other overlap tests in `test_generation.py`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/generation_engine
git commit -m "refactor: extract effective_fields/build_overlap_pool into overlap.py"
```

---

### Task 6: Extract `persistence.py`

**Files:**
- Create: `backend/app/services/generation_engine/persistence.py`
- Modify: `backend/app/services/generation_engine/engine.py` (remove `_infer_duckdb_types` and the duplicated table-creation + metadata-insert blocks; import the new functions)

**Interfaces:**
- Consumes: `app.schemas.generation.{DatasetDefinition, DatasetResult, FieldDefinition}`.
- Produces: `infer_duckdb_types(fields) -> list[str]`, `create_table(db, table_name, column_names, col_types) -> None`, `persist_dataset_metadata(db, definition, dataset_id, table_name, run_id, homogeneity, master_seed, actual_count, column_names) -> DatasetResult` — used by `flat.py` and `grouped.py` (Task 8).

- [ ] **Step 1: Create `persistence.py`**

```python
from __future__ import annotations

import json
import logging

from app.schemas.generation import DatasetDefinition, DatasetResult, FieldDefinition

logger = logging.getLogger(__name__)


def infer_duckdb_types(fields: list[FieldDefinition]) -> list[str]:
    type_map: list[str] = []
    for f in fields:
        t = f.type.lower()
        if t in ("integer", "int"):
            type_map.append("BIGINT")
        elif t in ("float", "decimal", "number"):
            type_map.append("DOUBLE")
        elif t == "boolean":
            type_map.append("BOOLEAN")
        elif t == "date":
            type_map.append("DATE")
        elif t in ("datetime", "timestamp"):
            type_map.append("TIMESTAMP")
        else:
            logger.debug("Unrecognized field type '%s' for field '%s', falling back to VARCHAR", f.type, f.name)
            type_map.append("VARCHAR")
    return type_map


def create_table(db, table_name: str, column_names: list[str], col_types: list[str]) -> None:
    col_defs = ", ".join(
        f'"{name}" {dtype}' for name, dtype in zip(column_names, col_types, strict=False)
    )
    db.execute(f'CREATE TABLE "{table_name}" ({col_defs})')


def persist_dataset_metadata(
    db,
    definition: DatasetDefinition,
    dataset_id: str,
    table_name: str,
    run_id: int,
    homogeneity: int,
    master_seed: int,
    actual_count: int,
    column_names: list[str],
) -> DatasetResult:
    columns_json = json.dumps(column_names)
    db.execute(
        """
        INSERT INTO metadata_runs (name, template_name, row_count, homogeneity, seed)
        VALUES (?, ?, ?, ?, ?)
        """,
        [definition.name, definition.template or "", actual_count, homogeneity, master_seed],
    )
    db.execute(
        """
        INSERT INTO metadata_datasets (dataset_id, run_id, name, table_name, columns_json, row_count, homogeneity, seed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [dataset_id, run_id, definition.name, table_name, columns_json, actual_count, homogeneity, master_seed],
    )
    return DatasetResult(
        dataset_id=dataset_id,
        name=definition.name,
        table_name=table_name,
        row_count=actual_count,
        columns=column_names,
    )
```

- [ ] **Step 2: Wire `persistence.py` into `engine.py`**

Delete `_infer_duckdb_types`. In both the flat and grouped generation functions:
- Replace the `CREATE TABLE` block (`col_defs = ...` + `db.execute(f'CREATE TABLE ...')`) with `create_table(db, table_name, column_names, col_types)`.
- Replace `_infer_duckdb_types(...)` calls with `infer_duckdb_types(...)`.
- Replace the trailing `metadata_runs`/`metadata_datasets` insert block + `DatasetResult(...)` construction (both functions end with an identical block) with:
```python
return persist_dataset_metadata(
    db, definition, dataset_id, table_name, run_id, homogeneity, master_seed, actual_count, column_names
)
```
Add `from app.services.generation_engine.persistence import create_table, infer_duckdb_types, persist_dataset_metadata` to the imports.

- [ ] **Step 3: Run the full suite to confirm no regression**

Run: `uv run pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/generation_engine
git commit -m "refactor: extract table creation and metadata persistence into persistence.py"
```

---

### Task 7: Extract `row_builder.py` (unify the two duplicate row implementations)

**Files:**
- Create: `backend/app/services/generation_engine/row_builder.py`
- Modify: `backend/app/services/generation_engine/engine.py` (replace the flat path's inline row loop body and the grouped path's `_gen_row` closure with calls to `generate_row`)

**Interfaces:**
- Consumes: `check_condition` (`conditions.py`, Task 3), `generate_field_value` (`generators.py`, Task 2).
- Produces: `generate_row(fields, fakers, fake_fallback, pool_entry=None, row_prefix=None, shared_key_pool=None) -> list` — used by `flat.py` and `grouped.py` (Task 8).

**Judgment call on a pre-existing inconsistency:** today's flat path logs formula-render failures (`logger.exception(...)`) but the grouped path's `_gen_row` closure silently swallows them. Unifying into one implementation means picking one. This plan keeps the logging — it's a log-only addition with no effect on generated data or control flow, and it removes a silent-failure blind spot in the grouped path. Flag this if reviewing against the spec: it's a minor behavioral note the spec didn't anticipate, not a deviation from anything the spec promised.

- [ ] **Step 1: Create `row_builder.py`**

```python
from __future__ import annotations

import logging
import random

from faker import Faker
from jinja2 import Template as JinjaTemplate

from app.schemas.generation import FieldDefinition
from app.services.generation_engine.conditions import check_condition
from app.services.generation_engine.generators import generate_field_value

logger = logging.getLogger(__name__)


def generate_row(
    fields: list[FieldDefinition],
    fakers: list[Faker | None],
    fake_fallback: Faker,
    pool_entry: dict | None = None,
    row_prefix: list | None = None,
    shared_key_pool: list | None = None,
) -> list:
    row = list(row_prefix) if row_prefix else []
    pool_entry = pool_entry or {}
    for fi, field in enumerate(fields):
        if field.name in pool_entry:
            row.append(pool_entry[field.name])
            continue

        if field.null_probability and random.random() < field.null_probability:
            row.append(None)
            continue

        if field.condition:
            if not check_condition(field.condition, row, fields):
                row.append(None)
                continue

        if field.generator == "shared_key" and shared_key_pool is not None:
            val = random.choice(shared_key_pool) if shared_key_pool else None
            row.append(val)
            continue

        if field.generator == "formula":
            try:
                t = JinjaTemplate(field.formula or "")
                already = {f.name: row[idx] for idx, f in enumerate(fields[:fi])}
                row.append(t.render(**already))
            except Exception:
                logger.exception("Formula evaluation failed for field '%s'", field.name)
                row.append(field.formula or "")
            continue

        fk = fakers[fi] or fake_fallback
        row.append(generate_field_value(fk, field, None))
    return row
```

- [ ] **Step 2: Replace the flat path's inline row loop**

In the flat generation function's batch loop, replace the per-field `for fi, field in enumerate(fields): ...` block with:
```python
row = generate_row(
    fields,
    field_fakers,
    fake,
    pool_entry=pool_entry,
    shared_key_pool=shared_key_pool,
)
```
(`pool_entry` is still computed the same way from `pool[row_idx]` just before this call.)

- [ ] **Step 3: Replace the grouped path's `_gen_row` closure**

Delete the local `_gen_row` function definition entirely. Replace its 4 call sites with `generate_row(...)`:
- `parent_row = _gen_row(parent_fields, parent_fakers)` → `parent_row = generate_row(parent_fields, parent_fakers, fake)`
- `child_row = _gen_row(child_fields, child_fakers, pool_entry=pool_entry)` (both occurrences — inside the grouped-rows loop and the flat-rows loop) → `child_row = generate_row(child_fields, child_fakers, fake, pool_entry=pool_entry)`

Add `from app.services.generation_engine.row_builder import generate_row` to the imports.

- [ ] **Step 4: Run the full suite — this is the critical unification check**

Run: `uv run pytest tests/ -v`
Expected: all PASS. This is the step most likely to surface a subtle behavioral mismatch between the two original implementations (beyond the formula-logging one already called out) — if anything fails here, diff the failing test's expected vs actual output against both original implementations before changing `row_builder.py`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/generation_engine
git commit -m "refactor: unify flat and grouped row generation into row_builder.py"
```

---

### Task 8: Split what remains into `flat.py`, `grouped.py`, `engine.py`

**Files:**
- Create: `backend/app/services/generation_engine/flat.py`
- Create: `backend/app/services/generation_engine/grouped.py`
- Modify: `backend/app/services/generation_engine/engine.py` (keep only `generate_datasets`; import `generate_dataset` from `flat.py`, `generate_grouped_dataset` from `grouped.py`)

**Interfaces:**
- Consumes: `build_field_fakers` (`fakers.py`), `create_table`/`infer_duckdb_types`/`persist_dataset_metadata` (`persistence.py`), `generate_row` (`row_builder.py`).
- Produces: `flat.generate_dataset(fake, definition, run_id, homogeneity, master_seed, overlap_pool=None) -> DatasetResult`, `grouped.generate_grouped_dataset(fake, definition, run_id, homogeneity, master_seed, overlap_pool=None) -> DatasetResult` — same signatures as today's `_generate_dataset`/`_generate_grouped_dataset`, used only by `engine.py`.

- [ ] **Step 1: Create `flat.py`**

```python
from __future__ import annotations

import logging
import uuid

from faker import Faker

from app.core.database import DuckDBManager
from app.core.validation import validate_column_name, validate_table_name
from app.schemas.generation import DatasetDefinition, DatasetResult
from app.services.generation_engine.fakers import build_field_fakers
from app.services.generation_engine.persistence import (
    create_table,
    infer_duckdb_types,
    persist_dataset_metadata,
)
from app.services.generation_engine.row_builder import generate_row

logger = logging.getLogger(__name__)


def generate_dataset(
    fake: Faker,
    definition: DatasetDefinition,
    run_id: int,
    homogeneity: int,
    master_seed: int,
    overlap_pool: list[dict] | None = None,
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

    field_fakers = build_field_fakers(fields, homogeneity, master_seed)

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
            row = generate_row(
                fields,
                field_fakers,
                fake,
                pool_entry=pool_entry,
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

- [ ] **Step 2: Create `grouped.py`**

```python
from __future__ import annotations

import random
import uuid

from faker import Faker

from app.core.database import DuckDBManager
from app.core.validation import validate_column_name, validate_table_name
from app.schemas.generation import DatasetDefinition, DatasetResult
from app.services.generation_engine.fakers import build_field_fakers
from app.services.generation_engine.persistence import (
    create_table,
    infer_duckdb_types,
    persist_dataset_metadata,
)
from app.services.generation_engine.row_builder import generate_row


def generate_grouped_dataset(
    fake: Faker,
    definition: DatasetDefinition,
    run_id: int,
    homogeneity: int,
    master_seed: int,
    overlap_pool: list[dict] | None = None,
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

    dataset_id = str(uuid.uuid4())
    table_name = f"dataset_{dataset_id}"
    validate_table_name(table_name)

    all_fields = parent_fields + child_fields
    column_names = [validate_column_name(f.name) for f in all_fields]
    column_names.append("parent_id")
    col_types = infer_duckdb_types(all_fields) + ["VARCHAR"]

    db = DuckDBManager.get_instance()
    create_table(db, table_name, column_names, col_types)

    parent_fakers = build_field_fakers(parent_fields, homogeneity, master_seed, namespace="parent_")
    child_fakers = build_field_fakers(child_fields, homogeneity, master_seed, namespace="child_")

    batch_size = 5000
    columns_formatted = ", ".join(f'"{c}"' for c in column_names)
    placeholders = ", ".join(["?"] * len(column_names))
    insert_sql = f'INSERT INTO "{table_name}" ({columns_formatted}) VALUES ({placeholders})'

    batch_data: list[list] = []
    pool = overlap_pool or []
    row_idx = 0

    # Distribute grouped_rows randomly across num_groups
    if num_groups > 0 and grouped_rows > 0:
        raw_weights = [random.random() for _ in range(num_groups)]
        total_weight = sum(raw_weights)
        group_sizes = [max(1, int(grouped_rows * w / total_weight)) for w in raw_weights]
        diff = grouped_rows - sum(group_sizes)
        for i in range(abs(diff)):
            group_sizes[i % num_groups] += 1 if diff > 0 else -1
        group_sizes = [max(1, s) for s in group_sizes]

        for g_idx in range(num_groups):
            parent_id = str(uuid.uuid4())
            parent_row = generate_row(parent_fields, parent_fakers, fake)

            child_count = group_sizes[g_idx]
            for _ in range(child_count):
                pool_entry = pool[row_idx] if row_idx < len(pool) else {}
                row_idx += 1
                child_row = generate_row(child_fields, child_fakers, fake, pool_entry=pool_entry)
                batch_data.append(parent_row + child_row + [parent_id])

                if len(batch_data) >= batch_size:
                    db.executemany(insert_sql, batch_data)
                    batch_data = []

    # Flat rows
    for _ in range(flat_rows):
        parent_row = generate_row(parent_fields, parent_fakers, fake)
        pool_entry = pool[row_idx] if row_idx < len(pool) else {}
        row_idx += 1
        child_row = generate_row(child_fields, child_fakers, fake, pool_entry=pool_entry)
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

- [ ] **Step 3: Reduce `engine.py` to just `generate_datasets`**

Delete the flat generation function and the grouped generation function bodies from `engine.py` entirely (they now live in `flat.py`/`grouped.py`). The file should contain only imports and `generate_datasets`:

```python
from __future__ import annotations

import random

from faker import Faker

from app.core.database import DuckDBManager
from app.schemas.generation import DatasetResult, GenerateRequest, GenerateResponse
from app.services.generation_engine.flat import generate_dataset
from app.services.generation_engine.grouped import generate_grouped_dataset
from app.services.generation_engine.overlap import build_overlap_pool, effective_fields


def generate_datasets(request: GenerateRequest) -> GenerateResponse:
    master_seed = request.seed if request.seed is not None else random.randint(0, 2**31 - 1)
    main_fake = Faker()
    main_fake.seed_instance(master_seed)
    random.seed(master_seed)

    # Validate overlap config before touching DuckDB
    overlap_ratio = request.overlap_ratio
    exact_field_names = set(request.exact_fields)
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
            )
        else:
            dr = generate_dataset(
                fake=main_fake,
                definition=dataset_def,
                run_id=run_id,
                homogeneity=request.homogeneity,
                master_seed=master_seed,
                overlap_pool=overlap_pool,
            )
        dataset_results.append(dr)

    return GenerateResponse(
        run_id=run_id,
        homogeneity=request.homogeneity,
        seed=master_seed,
        datasets=dataset_results,
        overlap_pool_size=pool_size,
        exact_fields=list(exact_field_names),
    )
```

- [ ] **Step 4: Run the full suite to confirm no regression**

Run: `uv run pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 5: Verify `engine.py` has no leftover dead imports**

Run: `cd backend && uv run python -c "import ast, sys; tree = ast.parse(open('app/services/generation_engine/engine.py').read()); print('parses OK')"`
Expected: `parses OK`. Then eyeball `engine.py`'s import block — it should only import what `generate_datasets` itself uses (`random`, `Faker`, `DuckDBManager`, the schema types, and the 4 `generation_engine.*` submodule imports above).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/generation_engine
git commit -m "refactor: split flat and grouped generation into flat.py and grouped.py"
```

---

### Task 9: Final verification

**Files:**
- None (verification only).

- [ ] **Step 1: Run the full backend suite one more time**

Run: `uv run pytest tests/ -v`
Expected: all PASS — same test count and outcomes as the Task 1 baseline.

- [ ] **Step 2: Confirm every module in the target structure exists and engine.py stayed small**

Run: `wc -l backend/app/services/generation_engine/*.py`
Expected: 9 files (`__init__.py`, `generators.py`, `conditions.py`, `fakers.py`, `overlap.py`, `persistence.py`, `row_builder.py`, `flat.py`, `grouped.py`, `engine.py` — 10 total including `engine.py`), each well under the original 591-line monolith, no file re-growing back into a everything-in-one-place shape.

- [ ] **Step 3: Confirm external imports still work unchanged**

Run: `cd backend && uv run python -c "from app.services.generation_engine import generate_datasets; from app.services import generation_engine; print(generation_engine.generate_datasets is generate_datasets)"`
Expected: `True`.

- [ ] **Step 4: Confirm the CLI and TUI entry points still import cleanly**

Run: `cd backend && uv run python -c "from app.services.generation_engine import generate_datasets as _; import cli.generate; import tui.screens.generation; print('imports OK')"`
Expected: `imports OK`.

- [ ] **Step 5: Commit** (only if Steps 1–4 surfaced any fix-up changes; otherwise this task is verification-only and there's nothing new to commit)
