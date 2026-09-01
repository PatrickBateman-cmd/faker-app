# Generation Engine Refactor

**Date:** 2026-08-31
**Status:** Approved
**Scope:** Backend only — `backend/app/services/generation_engine.py` → `backend/app/services/generation_engine/` package. No behavior change, no API change.

---

## Motivation

`generation_engine.py` has grown to 591 lines by accretion (flat generation → grouped generation → overlap pooling → grouped overlap). The two dataset-generation paths, `_generate_dataset` (flat) and `_generate_grouped_dataset` (grouped), duplicate almost everything:

- Table creation + `_infer_duckdb_types`.
- The per-field Faker/homogeneity-seeding loop — done three separate times (flat fields, parent fields, child fields), identical except for the string used in `hash(...)` to derive a per-field seed.
- The `metadata_runs` / `metadata_datasets` inserts and `DatasetResult` construction.
- The per-row generation logic (null_probability, `condition`, formula rendering, overlap pool-entry override, generator dispatch) — implemented twice independently: an inline loop in `_generate_dataset`, and the `_gen_row` closure inside `_generate_grouped_dataset`.

`_generate_field_value` is also a 90-line if/elif chain dispatching on `field.generator`, which doesn't scale and can't be unit-tested per generator.

Only `generate_datasets` is imported by any caller (`app/routers/generation.py`, `backend/tui/screens/generation.py`, `backend/cli/generate.py`, and all 4 backend test files that touch generation) — no other function in the module is imported externally. This means the module can be restructured freely as long as `generate_datasets` keeps working identically.

## Non-goals

- No change to `generate_datasets`' behavior, signature, or the `GenerateRequest`/`GenerateResponse` schemas.
- No change to what's supported (e.g. grouped datasets still don't support `shared_key` fields — see "Behavior to preserve, not fix" below).
- Not touching `iso20022_service.py`, the frontend components, or any other file flagged during scoping — those are separate future work if pursued.
- Not the planned Rust/PyO3 migration (`MIGRATION.md`) — this refactor only shapes the Python code so that migration is more mechanical later; it doesn't start it.

---

## Target structure

`backend/app/services/generation_engine.py` (single file) becomes a package:

```
backend/app/services/generation_engine/
  __init__.py       # from .engine import generate_datasets  (only re-export)
  generators.py      # GENERATOR_REGISTRY, generate_field_value(), apply_constraint()
  conditions.py       # check_condition(), formula rendering
  fakers.py            # build_field_fakers(fields, homogeneity, master_seed, namespace="")
  overlap.py            # effective_fields(), build_overlap_pool()
  row_builder.py         # generate_row(fields, fakers, fake_fallback, pool_entry=None, row_prefix=None, shared_key_pool=None)
  persistence.py          # create_table(), infer_duckdb_types(), persist_dataset_metadata()
  flat.py                  # generate_dataset() — today's _generate_dataset
  grouped.py                # generate_grouped_dataset() — today's _generate_grouped_dataset
  engine.py                  # generate_datasets() — validation + orchestration, today's top-level function
```

Every existing import (`from app.services.generation_engine import generate_datasets`, `from app.services import generation_engine`) keeps working unchanged because `__init__.py` re-exports `generate_datasets`.

### `generators.py`

Replaces the if/elif chain with a registry:

```python
GENERATOR_REGISTRY: dict[str, Callable[[Faker], object]] = {
    "first_name": lambda fake: fake.first_name(),
    "email": lambda fake: fake.email(),
    ...
}

def generate_field_value(fake, field, constraint):
    cons = constraint or field.constraint
    gen = field.generator
    if gen in ("formula", "shared_key"):
        ...  # unchanged special-cased returns
    handler = GENERATOR_REGISTRY.get(gen)
    if handler is None:
        logger.warning(...)
        return apply_constraint(fake, fake.word(), cons)
    return apply_constraint(fake, handler(fake, cons), cons)
```

Generators whose output depends on `cons` (`random_int`, `pydecimal`, `bothify`, `random_element`, `text`, `date_between`, `date_of_birth`) take `cons` as a parameter; the rest ignore it. `uuid4`/`uuid_int` bypass `apply_constraint` exactly as they do today (no min/max clamp on UUIDs).

### `fakers.py`

```python
def build_field_fakers(fields: list[FieldDefinition], homogeneity: int, master_seed: int, namespace: str = "") -> list[Faker | None]:
    ...
```

Replaces all three duplicated seeding loops. Call sites: `flat.py` calls with `namespace=""` (reproducing today's `hash(field.name)`), `grouped.py` calls twice with `namespace="parent_"` and `namespace="child_"` (reproducing `hash(f"parent_{field.name}")` / `hash(f"child_{field.name}")`). This exact reproduction matters — see Testing below.

### `row_builder.py`

```python
def generate_row(fields, fakers, fake_fallback, pool_entry=None, row_prefix=None, shared_key_pool=None) -> list:
    ...
```

Single implementation of the per-field row-building steps (pool override → null_probability → condition → shared_key → formula → generator dispatch), used by both `flat.py` and `grouped.py`. `grouped.py`'s call sites omit `shared_key_pool` (stays `None`), preserving that grouped datasets don't support `shared_key` fields today (see below).

### `persistence.py`

```python
def create_table(db, table_name, column_names, col_types) -> None
def infer_duckdb_types(fields: list[FieldDefinition]) -> list[str]
def persist_dataset_metadata(db, definition, dataset_id, table_name, run_id, homogeneity, master_seed, actual_count, column_names) -> DatasetResult
```

`persist_dataset_metadata` replaces the duplicated `metadata_runs` + `metadata_datasets` insert block and `DatasetResult(...)` construction in both `flat.py` and `grouped.py`.

### `flat.py`, `grouped.py`, `engine.py`

Same responsibilities and signatures as today's `_generate_dataset`, `_generate_grouped_dataset`, `generate_datasets`, rebuilt on top of the shared modules above. `grouped.py` keeps its group-size-distribution logic (`raw_weights`/`group_sizes`) — that's genuinely grouped-only and doesn't move.

---

## Behavior to preserve, not fix

Two pre-existing quirks must survive the refactor unchanged (fixing them is out of scope):

1. **Grouped datasets don't support `shared_key` fields.** The flat path's row loop special-cases `generator == "shared_key"`; the grouped path's `_gen_row` never did. A `shared_key` field in a grouped dataset silently falls through to generic dispatch (`""` via `apply_constraint`). Preserved via `shared_key_pool` being an optional param the grouped call sites simply don't pass.
2. **Random draw order.** Seeded/deterministic tests (`homogeneity=100`, fixed `seed=`) depend on the exact sequence and count of `random.randint`/`random.random()` calls. `build_field_fakers` and `generate_row` must iterate fields and call `random.*` in the same order as today's code, or seeded tests will produce different (not wrong, just different) output and fail on exact-match assertions.

---

## Testing

- `backend/tests/test_generation.py` (298 lines — covers flat, grouped, overlap, and grouped-overlap end-to-end) must pass unmodified. Its import (`from app.services.generation_engine import generate_datasets`) doesn't change, so it's a black-box regression check on the whole package.
- `backend/tests/test_api.py`, `test_export.py`, `test_transform.py` (which import `generate_datasets` to set up fixtures) must also pass unmodified.
- Add focused unit tests for the newly-isolated pure modules, since they're now cheap to test in isolation:
  - `generators.py`: registry dispatch for a representative generator, and the unknown-generator fallback (`fake.word()` + warning).
  - `conditions.py`: `check_condition` operators (`>=`, `==`, `!=`, type-mismatch fallback).
  - Not exhaustive coverage of all 28 generators — just enough to lock in the extraction boundary.
- No new integration tests needed; this is a pure internal restructuring with no behavior change.

## Rollout

Single change, no migration/versioning concerns (internal Python module only, no DB schema, no API contract change). Land as one commit once tests pass.
