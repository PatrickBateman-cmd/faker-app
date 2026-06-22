# Overlapping Datasets Feature Design

**Date:** 2026-06-22  
**Status:** Approved  
**Scope:** Backend schema + generation engine + frontend controls

---

## Overview

Users can generate multiple datasets that share a controlled fraction of rows. A global `overlap_ratio` (0.0–1.0) determines what percentage of rows come from a shared pool. `exact_fields` names the fields whose values are identical across all datasets for those shared rows; all other fields regenerate independently per dataset.

**0.0** = no shared rows (existing behaviour, default).  
**1.0** = every row in the smallest dataset is drawn from the pool (the pool covers `min(row_counts)` rows).

---

## Schema & API

### `GenerateRequest` additions (`schemas/generation.py`)

```python
overlap_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
exact_fields: list[str] = Field(default_factory=list)
```

Both fields are optional. Default `overlap_ratio=0.0` preserves full backward compatibility.

### `GenerateResponse` additions

```python
overlap_pool_size: int     # actual shared row count (0 when no overlap)
exact_fields: list[str]    # echoed back for client confirmation
```

---

## Generation Engine (`services/generation_engine.py`)

### Pool construction

A new helper `_build_overlap_pool` runs once before the dataset loop:

```python
def _build_overlap_pool(
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
            entry[field.name] = _generate_field_value(fake, field, None)
        pool.append(entry)
    return pool
```

`pool_size = floor(overlap_ratio × min(d.rows for d in request.datasets))`

The pool is keyed from the first dataset's field definitions. `exact_fields` names must exist in every dataset — validated before generation starts.

### Row injection

`_generate_dataset` gains an `overlap_pool: list[dict]` parameter (default `[]`).

For each row at index `row_idx`:
- If `row_idx < len(overlap_pool)`: use `overlap_pool[row_idx][field.name]` for exact fields; generate normally for all other fields.
- If `row_idx >= len(overlap_pool)`: generate all fields normally (existing logic, unchanged).

### Scope restriction

Overlap is **flat datasets only**. If `overlap_ratio > 0` and any `DatasetDefinition` has `group_config` set, raise `ValueError` before any table is created.

---

## Error Handling

All validation runs before any DuckDB table is created — no partial cleanup needed.

| Condition | HTTP response |
|---|---|
| `overlap_ratio > 0` and `exact_fields` empty | 400: `"exact_fields must be specified when overlap_ratio > 0"` |
| `overlap_ratio > 0` and any dataset uses `group_config` | 400: `"overlap is not supported with grouped datasets"` |
| An `exact_fields` name not present in a dataset's fields | 400: `"exact field 'X' not found in dataset 'Y'"` |
| `floor(overlap_ratio × min_rows) == 0` | No error; `overlap_pool_size: 0` in response, treated as no overlap |

---

## Frontend (`components/GenerationControls/GenerationControls.tsx`)

Two new controls added to the existing top toolbar row:

**Overlap Ratio slider**  
- Range 0–100 (displayed as `%`), stored internally as float 0.0–1.0 for the API call.  
- Default 0. Mirrors the Homogeneity slider in visual style.

**Exact Fields text input**  
- Visible and enabled only when overlap > 0.  
- Comma-separated field names; split + trimmed before sending as `exact_fields: string[]`.  
- No client-side validation beyond basic split — server returns 400 on invalid names, surfaced via existing `generateMut.isError`.

**Results display**  
When `overlap_pool_size > 0` in the response, `GenerationResults` shows:  
`Shared pool: N rows  •  Exact fields: field_a, field_b`

No new files. All changes are within `GenerationControls.tsx` and `types/generation.ts`.

---

## What is not changing

- No new DuckDB tables or migrations. The pool is ephemeral (Python memory, discarded after the run).
- `_generate_grouped_dataset` is untouched.
- `homogeneity`, `seed`, and all existing `DatasetDefinition` fields are unchanged.
- The `shared_key` mechanism is separate and unaffected.

---

## Open questions / future work

- Overlap across grouped datasets is out of scope and blocked at validation time.
- If datasets have different field sets, `exact_fields` must be a subset of fields present in all datasets — validated per dataset before generation.
- Pool order is deterministic (generated with master seed), so the same seed + overlap_ratio always produces the same shared rows.
