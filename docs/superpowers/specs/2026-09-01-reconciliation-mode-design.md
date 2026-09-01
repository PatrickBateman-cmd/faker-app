# Reconciliation Mode — Intentional Breaks on Overlap Pools

**Date:** 2026-09-01
**Status:** Approved
**Scope:** Backend schema + generation engine + migrations + CLI
**Builds on:** [2026-06-22-overlapping-datasets-design.md](./2026-06-22-overlapping-datasets-design.md) and [2026-08-31-grouped-dataset-overlap-design.md](./2026-08-31-grouped-dataset-overlap-design.md), which implemented the `overlap_ratio` / `exact_fields` shared-pool mechanism this feature extends. Frontend is explicitly out of scope.

---

## Overview

Users generating up to 4 datasets in one `/generate` call want to treat them as independent "systems of record" (e.g. GL, sub-ledger, custodian, broker feed) that share a common key and mostly-matching attributes, so the batch can be loaded into an external reconciliation tool and tested. The existing overlap pool already gives perfect 1:1:1:1 field matching via `exact_fields`; what's missing is a way to deliberately *mismatch* a controlled fraction of rows on specific fields, know exactly which rows/fields were mismatched (ground truth), and have this behavior gated behind an explicit switch rather than silently changing existing overlap semantics.

`reconciliation_mode: bool` is that switch. Off (default), `/generate` behaves exactly as it does today — full backward compatibility, existing frontend untouched. On, the request is **locked** into reconciliation semantics: full pool coverage, a mandatory join key, and optional per-field intentional breaks recorded as ground truth.

---

## Schema & API (`schemas/generation.py`)

```python
class FieldBreakConfig(BaseModel):
    field_name: str
    break_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    break_style: Literal["drift", "different", "null"] = "drift"
    drift_pct: float = Field(default=0.02, gt=0.0, le=1.0)  # used only when break_style="drift"


class GenerateRequest(BaseModel):
    datasets: list[DatasetDefinition] = Field(..., min_length=1, max_length=4)
    homogeneity: int = Field(default=50, ge=1, le=100)
    seed: int | None = None
    overlap_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    exact_fields: list[str] = Field(default_factory=list)
    reconciliation_mode: bool = False
    field_breaks: list[FieldBreakConfig] = Field(default_factory=list)
```

`exact_fields[0]` is the **join key** when `reconciliation_mode=True` — it is always copied verbatim (never eligible for `field_breaks`), guaranteeing the 1:1:1:1 correspondence the reconciliation tool joins on.

### `GenerateResponse` additions

```python
break_count: int = 0   # total intentional breaks recorded across all datasets
```

(`run_id`, `overlap_pool_size`, `exact_fields` already exist and are reused as-is.)

### Locking validation (`generate_datasets`, before any DuckDB table is created)

| Condition | Response |
|---|---|
| `reconciliation_mode=True` and `len(datasets) < 2` | 400: reconciliation requires at least 2 datasets |
| `reconciliation_mode=True` and `exact_fields` empty | 400: `exact_fields` (join key first) required |
| `reconciliation_mode=True` | `overlap_ratio` is **forced to `1.0`** server-side regardless of the request value — full coverage is implied by the mode, not separately configurable. Echoed back via `overlap_pool_size` in the response. |
| `reconciliation_mode=False` and `field_breaks` non-empty | 400: `field_breaks` requires `reconciliation_mode=True` |
| `field_breaks[i].field_name` not in `exact_fields` | 400: break fields must already be linked via `exact_fields` |
| `field_breaks[i].field_name == exact_fields[0]` | 400: the join key cannot carry a break |
| `field_breaks[i].break_style == "drift"` and field type not `integer`/`float`/`decimal` | 400: drift only valid on numeric fields |
| grouped dataset + `exact_fields` name a parent field | 400 (existing rule from the 2026-08-31 doc, unchanged and still enforced) |

---

## Generation Engine

### Break application — new `services/generation_engine/breaks.py`

Deliberately **not** a change to `row_builder.generate_row`'s signature or contract — breaks are applied as a post-processing pass on the row it already produced, keeping the existing pool-injection code and its test coverage untouched.

```python
def apply_field_breaks(
    row: list,
    fields: list[FieldDefinition],
    field_breaks: dict[str, FieldBreakConfig],
    join_key_value: object,
    dataset_id: str,
) -> list[BreakRecord]:
    breaks = []
    for fi, field in enumerate(fields):
        cfg = field_breaks.get(field.name)
        if cfg is None or random.random() >= cfg.break_rate:
            continue
        true_value = row[fi]
        row[fi] = _transform(true_value, field, cfg)
        breaks.append(BreakRecord(
            dataset_id=dataset_id, field_name=field.name,
            join_key_value=join_key_value, true_value=true_value, broken_value=row[fi],
            break_style=cfg.break_style,
        ))
    return breaks
```

`_transform` implements the three `break_style`s: `drift` (±`drift_pct` on the numeric value), `different` (a fresh independent draw from the field's own generator), `null` (`None`).

### Wiring (`engine.py`, `flat.py`, `grouped.py`)

- `engine.py`'s dataset loop changes from `for dataset_def in request.datasets` to `for idx, dataset_def in enumerate(request.datasets)`, threading `dataset_index=idx` and `field_breaks` (a `{field_name: FieldBreakConfig}` dict, only when `reconciliation_mode`) into both `generate_dataset` and `generate_grouped_dataset`.
- Dataset index `0` never receives `field_breaks` (it's the authoritative source the pool was built from) — only indices ≥1 do.
- In `flat.py`'s row loop, right after `row = generate_row(...)` (flat.py:83-89), call `apply_field_breaks(row, fields, field_breaks, join_key_value=row[join_key_col_idx], dataset_id=dataset_id)` when `field_breaks` is non-empty, and extend the run's `breaks` accumulator. `join_key_col_idx` is resolved once via `column_names.index(exact_fields[0])` before the batch loop.
- `grouped.py` gets the identical call, applied only to child rows (mirroring the existing parent-field exclusion from the 2026-08-31 doc) right after `_gen_row` produces each child row.
- `engine.py` collects all `BreakRecord`s across datasets and, if any exist, persists them in one `executemany` after all dataset tables are created (metadata writes happen after data writes, consistent with `persist_dataset_metadata`'s existing ordering).

---

## Ground Truth Persistence

New migration (next entry in `core/migrations.py`, run inside its own `BEGIN`/`COMMIT` like all others):

```sql
CREATE SEQUENCE IF NOT EXISTS seq_recon_break_id;

CREATE TABLE IF NOT EXISTS metadata_recon_breaks (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_recon_break_id'),
    run_id BIGINT NOT NULL,
    dataset_id VARCHAR NOT NULL,
    field_name VARCHAR NOT NULL,
    join_key_value VARCHAR,
    true_value VARCHAR,
    broken_value VARCHAR,
    break_style VARCHAR NOT NULL,
    created_at TIMESTAMP DEFAULT current_timestamp
);
```

A dedicated sequence, per the project's "do not mix sequences" convention — this table's inserts must never use `seq_run_id` or `seq_aggregation_id`. Values are stored as `VARCHAR` (stringified) since `true_value`/`broken_value` may be numeric, string, or null depending on the field type — this table is a read-only audit trail, not something queried by type.

### API

`GET /generate/runs/{run_id}/breaks` → `list[ReconBreakRecord]` (new Pydantic response model, one-to-one with the table columns). No CSV/parquet export pipeline — this table is small (bounded by `sum(rows) × break_rate` per field) and a JSON array is sufficient for both the CLI and any external tool to consume directly. Building a dedicated export path here would duplicate the existing dataset-export machinery for a fundamentally different (small, structured, non-tabular-dataset) artifact — explicitly deferred as YAGNI.

---

## CLI (`cli/generate.py`)

None of `overlap_ratio`, `exact_fields`, `reconciliation_mode`, or `field_breaks` currently have CLI flags — all are added together:

- `--reconciliation-mode` (flag)
- `--exact-fields "trade_id,amount"` (comma-separated; first entry is the join key)
- `--field-breaks-json '[{"field_name":"amount","break_rate":0.1,"break_style":"drift","drift_pct":0.02}]'`
- `--overlap-ratio` is accepted for the non-reconciliation use case (closing the existing gap) but is rejected with a clear CLI error if passed alongside `--reconciliation-mode` (server would silently override it — the CLI fails fast instead so the flag combination isn't misleading).

New command: `uv run faker breaks <run_id>` — calls the new endpoint and prints the ground truth as a table (or `--json` for raw output), so it can be redirected to a file for later scoring against the reconciliation tool's output.

---

## Testing

- **Schema validation** (`backend/tests/test_generation_schema.py` or similar): each row of the locking-validation table above gets a test — missing `exact_fields`, `field_breaks` without `reconciliation_mode`, break on the join key, break on a field not in `exact_fields`, `drift` on a non-numeric field, `< 2` datasets.
- **Engine — deterministic bounds**: 3 flat datasets, `reconciliation_mode=True`, `exact_fields=["trade_id","amount"]`, one `field_breaks` entry on `amount` with `break_rate=1.0` → assert `trade_id` matches exactly across all 3 datasets for every row, `amount` on datasets 1-2 differs from dataset 0 for every row and stays within `drift_pct`, and `metadata_recon_breaks` has exactly `rows × 2` rows (2 non-authoritative datasets).
- **Engine — no breaks**: same setup with `break_rate=0.0` → all fields match exactly, zero rows written to `metadata_recon_breaks`.
- **Grouped datasets**: mirrors the existing `test_overlap_grouped_*` tests — a child-level field with breaks behaves as above; a parent-level field in `exact_fields` under `reconciliation_mode` is still rejected by the pre-existing check.
- **Ground truth endpoint**: `GET /generate/runs/{run_id}/breaks` returns the persisted records for a run, empty list for a run with no breaks.
- **CLI**: smoke test for `faker generate --reconciliation-mode ...` and `faker breaks <run_id>`.

---

## What is not changing

- `overlap_ratio`/`exact_fields` behavior when `reconciliation_mode=False` — byte-for-byte identical to the 2026-06-22 and 2026-08-31 designs. The existing frontend (`GenerationControls.tsx`) sends neither `reconciliation_mode` nor `field_breaks`, so it is entirely unaffected.
- `row_builder.generate_row`'s signature and pool-injection logic (flat.py:83-89, `row_builder.py:26-28`) — untouched; breaks are a separate post-processing step.
- The unrelated `shared_key`/`SharedKeyConfig` mechanism (samples from an already-persisted external dataset) — different feature, not touched.
- No frontend changes (explicitly out of scope per this feature's requirements).

---

## Open questions / future work

- `break_style="different"` for non-numeric fields draws from the field's own generator/constraints, which could — by chance — redraw the same value as the true one; not treated as a bug (a real recon tool would also occasionally see "different" systems agree by coincidence), but worth noting if test flakiness shows up.
- Parent-field breaks for grouped datasets remain out of scope, consistent with the existing parent-field overlap restriction.
