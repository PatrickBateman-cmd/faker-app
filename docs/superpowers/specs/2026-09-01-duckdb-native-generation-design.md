# DuckDB-Native Generation Fast Path

**Date:** 2026-09-01
**Status:** Approved
**Scope:** Backend only — `backend/app/services/generation_engine/` (the package from the 2026-08-31 refactor). No API/schema change.
**Branch:** `worktree-duckdb-native-generation` (forked from the generation-engine-refactor branch, which this depends on — see Dependencies)

---

## Motivation

Dataset generation currently calls Faker once per field, per row, in a Python loop (`row_builder.py`'s `generate_row`), then batches inserts via `executemany`. For a large fraction of field types — plain numeric ranges, booleans, UUIDs — this is doing expensive, GIL-bound, per-value Python work for output that DuckDB's own vectorized engine can produce in bulk, in C++, an order of magnitude faster.

This was chosen over three alternatives (full Rust/Go backend rewrite, NumPy vectorization, PyO3 hot-loop extension per `MIGRATION.md`) because:
- It attacks the real scalability constraint in this app — `DuckDBManager`'s `RLock` serializes *every* DB operation in-process, so shrinking per-request CPU time (lock-hold time) is the highest-leverage lever available, more than raw generation throughput alone.
- It requires no new language, toolchain, or dependency — DuckDB is already a hard dependency.
- It doesn't foreclose the PyO3 path later for whatever remains Python-only (Faker-only generators) — if anything, it shrinks that surface.

## Non-goals

- Not a full rewrite of anything. Not touching routers, schemas, DuckDB core, or any file outside `generation_engine/`.
- Not attempting horizontal scalability (multiple app instances against one DuckDB file) — that requires swapping the storage engine, a much larger decision, out of scope here.
- **v1 covers a narrow generator subset only** (see Scope below) — not all 31 generators. Deliberately conservative: ship the simple, mechanically-verifiable cases first, validate the approach, expand later.
- Not preserving byte-identical output for migrated generators — see "Behavior change" below. This is explicitly not a repeat of the prior refactor's "zero behavior change" contract.

## Dependencies

This spec assumes the 2026-08-31 generation-engine-refactor package structure (`generators.py`, `row_builder.py`, `fakers.py`, `flat.py`, `grouped.py`) already exists. That work is on an open PR (#1), not yet merged to `main`. This branch was fast-forwarded onto that PR's branch tip so the package exists to build on — **this branch cannot be merged to `main` before PR #1 is**, or the merge will conflict/reintroduce the monolithic file. Track this dependency explicitly when this branch's own PR is opened.

---

## Scope: which generators move to SQL in v1

| Generator | v1 SQL-eligible? | Why |
|---|---|---|
| `random_int`, `pyint` | ✅ | Pure numeric range, trivial SQL |
| `pydecimal` | ✅ | Numeric range + rounding, trivial SQL |
| `boolean` | ✅ | Trivial SQL |
| `uuid4` | ✅ | DuckDB has a native `uuid()` function |
| `uuid_int` | ✅ | Approximable as a random 63-bit positive int (see Behavior change) |
| `date_between`, `date_of_birth`, `date_time` | ❌ v2 | Needs relative-date-string parsing (`"-5y"`, `"today"`) into concrete literals before templating SQL — real but deferrable complexity |
| `random_element` | ❌ v2 | Weighted variant needs a dynamically-built `CASE WHEN` over cumulative probability ranges — more moving parts, not needed to validate the core mechanism |
| `currency_code` | ❌ v2 | Needs a hardcoded ISO 4217 list to match Faker's value set; low value to rush |
| everything else (name/email/address/company/text/bothify/swift/iban/bban/word/formula/shared_key) | ❌ never | Faker-only, no honest SQL equivalent, or has cross-field semantics that must stay Python |

v1 is 5 of 31 generators. That's deliberately small — it's enough to prove the mechanism (eligibility rule, precomputed-value injection, SQL-side determinism) end to end on the simplest possible cases, with the harder ones (date parsing, weighted lists) queued as follow-up specs once the pattern is validated in production.

---

## Architecture

### Eligibility rule

A field takes the SQL fast path **only if all of these hold**:
1. `field.generator` is in the v1 SQL set above.
2. `field.condition` is not set.
3. `field.generator != "formula"`.
4. `field.generator != "shared_key"`.
5. `field.name` is not in the request's `exact_fields` (i.e., not part of an active overlap pool).

Anything failing any check goes through the existing, unmodified `generate_row()` Python path. This keeps every piece of order-dependent or cross-field logic (condition evaluation, formula rendering, shared_key pooling, overlap pool injection) completely untouched — only field-independent, single-column generation moves.

### Mechanism: precomputed columns merged into `pool_entry`

Rather than splitting the table write (INSERT some columns, UPDATE others — rejected; row correlation across separate statements is unnecessary complexity), the SQL-eligible fields are bulk-generated **before** the row loop starts, as plain Python lists, then fed into the existing per-row loop through the same mechanism `pool_entry` already uses.

New module `sql_generators.py`:

```python
def is_sql_eligible(field: FieldDefinition, exact_field_names: set[str]) -> bool:
    return (
        field.generator in SQL_GENERATOR_REGISTRY
        and not field.condition
        and field.generator not in ("formula", "shared_key")
        and field.name not in exact_field_names
    )

def build_sql_columns(
    db,
    fields: list[FieldDefinition],
    rows: int,
    field_seeds: dict[str, int | None],
) -> dict[str, list]:
    """One DuckDB SELECT per column (see Determinism below for why not one bulk multi-column SELECT).
    Returns {field_name: [value, value, ...]} of length `rows`, in field order."""
```

At each call site in `flat.py`/`grouped.py`'s row loop, the per-row slice of precomputed values is merged into the same dict `generate_row()` already special-cases:

```python
sql_row_entry = {name: values[row_idx] for name, values in sql_columns.items()}
row = generate_row(
    fields, field_fakers, fake,
    pool_entry={**sql_row_entry, **pool_entry},  # pool_entry wins on the (never-occurring) collision
    shared_key_pool=shared_key_pool,
)
```

**`generate_row()` itself needs zero changes.** Its existing `if field.name in pool_entry: row.append(pool_entry[field.name]); continue` branch (checked before `null_probability`) already does exactly what's needed — the eligibility rule guarantees no overlap-pool field is ever also SQL-eligible, so the two dicts never actually collide in practice; the merge order is just defensive.

`null_probability` for SQL-eligible fields is folded into the generation SQL itself (`CASE WHEN random() < p THEN NULL ELSE <expr> END`), so it's applied exactly once — Python's `null_probability` check is bypassed for these fields the same way it already is for pool-entry fields today.

### Determinism (verified against installed DuckDB 1.5.3)

Confirmed directly (see spec review notes below) two facts DuckDB's docs don't make obvious:
1. `SELECT setseed(x)` followed by `random()` calls is fully deterministic and reproducible — same seed, same sequence, verified with three repeated runs.
2. **A single SQL statement's `random()` calls share one continuous stream** — `SELECT random() AS a, random() AS b FROM range(n)` does *not* give column `a` and column `b` independent seeds. Independent per-column seeding requires **separate statements**: `setseed(s1)` + a single-column generate/`UPDATE` for column A, then `setseed(s2)` + the same for column B.

This means `build_sql_columns` issues **one SQL statement per SQL-eligible field**, not one bulk multi-column statement — more round-trips than a single `INSERT ... SELECT`, but each is still a single vectorized DuckDB call over all `rows` values at once, vastly cheaper than a Python-side loop of `rows` Faker calls. For a master-seeded field, that statement is preceded by `setseed(<derived-from-field_seed>)`; for a non-master field, no `setseed` call — it draws from DuckDB's ambient RNG state, mirroring how non-master Python fields today share the single unseeded `fake` instance.

`field_seeds` (the `dict[str, int | None]` passed into `build_sql_columns`) reuses the exact homogeneity-roll mechanism `fakers.py`'s `build_field_fakers` already implements — `fakers.py` gains a small extraction, `roll_field_seeds(fields, homogeneity, master_seed, namespace="") -> list[int | None]`, that `build_field_fakers` becomes a thin wrapper around (unseeded fields → `None`, master-seeded fields → the derived `field_seed` int).

**`roll_field_seeds` is called exactly once, over the full `fields` list in original order** — identical to today's single `build_field_fakers` pass, zero change to `random.randint` call count or order. Its output feeds *two* consumers: `build_sql_columns` reads the seed for each SQL-eligible field (by name); `build_field_fakers` (now built on top of the same seed list) converts every seed — SQL-eligible fields included — into a `Faker` instance, matching today's array shape exactly. The `Faker` instances built for SQL-eligible fields are simply never read (the `pool_entry` merge means `generate_row`'s `fields[fi]` branch for those fields is short-circuited before it reaches `fakers[fi]`), which costs a handful of unused `Faker()` instantiations but keeps the roll mechanism **identical to today's, no relaxation needed**. This supersedes an earlier draft of this section that proposed rolling the two field groups separately — that would have changed call order between groups for no benefit once this simpler alternative was found.

### DuckDB SQL templates (v1 set)

| Generator | Template sketch |
|---|---|
| `random_int`/`pyint` | `CAST(FLOOR(random() * (:max - :min + 1)) + :min AS BIGINT)` |
| `pydecimal` | `ROUND(:min + random() * (:max - :min), :right_digits)` |
| `boolean` | `(random() < 0.5)` |
| `uuid4` | `CAST(uuid() AS VARCHAR)` |
| `uuid_int` | `CAST(random() * 9223372036854775807 AS BIGINT)` |

`:min`/`:max`/`:right_digits` come from `ConstraintConfig`, same defaults as today's `GENERATOR_REGISTRY` lambdas (e.g. `random_int` defaults to 0–999999). Exact syntax gets nailed down with real DuckDB queries during implementation (TDD), not finalized here.

---

## Behavior change (read this before approving)

Unlike the prior refactor, **this is not a zero-behavior-change migration**:

- SQL-generated values for eligible fields will differ from what Faker would have produced for the same seed — it's DuckDB's PRNG algorithm now, not Faker's/Python's `random` module's. Row counts, column types, constraint clamping (min/max/right_digits), null rates, and "same seed + same request → same output" determinism all still hold. The actual numbers won't match pre-migration output bit-for-bit.
- `uuid_int`'s derivation changes from "take a real UUID4's integer value, mask to 63 bits" to "draw a uniform random 63-bit integer directly." Both produce a positive `BIGINT` in the same range with effectively the same distribution properties (uniform); the exact bit-derivation algorithm differs.

If any downstream consumer depends on exact generated values matching across a Faker-vs-SQL boundary (e.g., a saved golden dataset, an external system matching on generated IDs), this migration would break that — worth confirming that's not a real usage pattern before proceeding. Based on this app's purpose (generating throwaway fake datasets for testing/dev), that risk looks low, but it's a product judgment, not an engineering one, so flagging it rather than assuming.

## Error handling

- If a SQL-eligible field's constraint values are malformed in a way that would break the generated SQL (e.g., non-numeric `min`/`max` on a `random_int` field — already guarded by Pydantic schema validation upstream, so this shouldn't be reachable, but `build_sql_columns` should raise a clear `ValueError` rather than let a malformed query hit DuckDB and surface a cryptic SQL error).
- If `build_sql_columns` fails for any reason after partial success (e.g., field 2 of 3 fails), no partial state has been written to the target table yet (columns are built as in-memory lists before any INSERT) — safe to let the exception propagate and abort the whole `generate_dataset`/`generate_grouped_dataset` call, consistent with today's all-or-nothing table creation.

## Testing

Same playbook as the prior refactor's final review, adapted for the fact that values are expected to change:

- **Statistical/property tests**, not byte-identical assertions: for each v1 SQL generator, assert type correctness, constraint bounds (min/max respected, right_digits respected), null rate is within a tolerance of the requested `null_probability` over a large sample, and — for `random_element`-style eligibility (not in v1, but establishing the pattern) — value membership in the allowed set.
- **Determinism test**: same seed + same request, run twice in the *same process*, assert identical output (this remains meaningful and testable, unlike cross-process reproducibility).
- **Eligibility-boundary tests**: a field with `condition`/`formula`/`shared_key`/`exact_fields` membership must NOT take the SQL path even if its generator is in the v1 set — verify by checking it still produces the Python-path's characteristic behavior (e.g., a `null_probability=1.0` + `condition` field pinned to the existing precedence order from the prior refactor's test suite).
- **Regression**: full existing 62-test suite must keep passing unmodified for every field NOT in the v1 SQL set (the majority) — those fields' code path doesn't change at all.
- **A/B property harness**: reuse the pattern from the prior refactor's final review (build both paths in one process, run against matched inputs) but compare *distributions* (e.g., a chi-square-ish sanity check on `boolean`'s ~50/50 split, min/max bounds over N samples) rather than exact values.

## Rollout

- Work happens on `worktree-duckdb-native-generation`, isolated from `main`. This repo currently has **no CI/CD pipeline configured** (confirmed — no `.github/workflows` or equivalent exists), so "isolate before deploy" in practice means: this branch/PR + the same subagent-driven task-and-final review process used for the prior refactor, before merge. Setting up an actual CI pipeline (run `pytest` on every PR) would close that gap — worth a separate, small follow-up, not bundled into this feature.
- Merge order: PR #1 (package refactor) must land first; this branch rebases onto `main` after that, not before.
- No schema/migration changes, no new dependencies (DuckDB is already required). Deployable as a normal code change once merged.
