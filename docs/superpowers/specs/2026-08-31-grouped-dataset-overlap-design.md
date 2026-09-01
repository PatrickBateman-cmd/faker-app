# Grouped Dataset Overlap Support

**Date:** 2026-08-31
**Status:** Implemented
**Scope:** Backend generation engine + validation + tests
**Follows up on:** [2026-06-22-overlapping-datasets-design.md](./2026-06-22-overlapping-datasets-design.md), which explicitly scoped overlap to flat datasets and listed grouped-dataset overlap as blocked/future work.

---

## Overview

The overlap pool (`overlap_ratio` + `exact_fields`) previously raised `ValueError("overlap is not supported with grouped datasets")` for any `DatasetDefinition` with `group_config` set. This change lifts that restriction for **child-level** fields — parent fields (which repeat across every child row of a group) remain unsupported, since injecting a pool value into a parent field would be inconsistent with how parent rows are generated once per group rather than once per row.

## Changes (`services/generation_engine.py`)

### `_effective_fields(ds)`

New helper returning the field list to validate/pool against for a given `DatasetDefinition`:
- Grouped dataset → `group_config.parent_fields + group_config.child_fields`
- Flat dataset → `ds.fields`

Used in place of the old direct `ds.fields` access in two places that previously assumed every dataset was flat:
- `exact_fields` membership validation in `generate_datasets`.
- Pool construction, which read `request.datasets[0].fields` — this broke (silently produced an empty pool) whenever the *first* dataset in the request was grouped, since grouped datasets carry no top-level `fields`. Covered by `test_overlap_pool_built_from_first_grouped_dataset`.

### Validation

For each grouped dataset, `exact_fields` entries are checked against `parent_fields` names; if any `exact_fields` name is a parent field, `generate_datasets` raises:
```
ValueError(f"exact field '{ef}' is a parent field in grouped dataset '{ds.name}'; overlap only supports child-level fields for grouped datasets")
```
This runs before any table is created, consistent with existing validation-first error handling.

### Row injection — `_generate_grouped_dataset`

- Gains an `overlap_pool: list[dict] | None = None` parameter, threaded through from `generate_datasets`.
- `_gen_row` gains a `pool_entry: dict | None` parameter; for each field, if `field.name` is a key in `pool_entry`, that value is used directly (skipping `null_probability` and normal generation) — mirroring the existing flat-dataset pool injection semantics.
- Pool entries are consumed by a single running `row_idx` counter shared across grouped rows and flat (ungrouped, `split_pct < 100`) rows within the dataset, so pool coverage spans the whole dataset in generation order, not just the grouped portion.
- Parent rows are never passed a `pool_entry` — only child rows receive one — enforcing the parent-field restriction at the generation layer as well as validation.

## Tests (`tests/test_generation.py`)

Three new tests:
- `test_overlap_grouped_child_field_matches_across_datasets` — two grouped datasets sharing `overlap_ratio=0.5` on a child field (`counterparty_id`) produce matching values for the first `pool_size` rows and distinct values after.
- `test_overlap_grouped_parent_field_rejected` — naming a parent field (`trade_id`) in `exact_fields` raises `ValueError` matching `"parent field"`.
- `test_overlap_pool_built_from_first_grouped_dataset` — regression test for the `_effective_fields` fix: a grouped dataset first in `request.datasets`, followed by a flat dataset, still builds a non-empty pool and matches values across both.

## What is not changing

- Flat-dataset overlap behavior (`_generate_dataset`) is untouched.
- Parent-field overlap remains unsupported — this is a deliberate restriction, not a gap to close later, per the reasoning above.
- No schema/API changes — `overlap_ratio`, `exact_fields`, `overlap_pool_size` are unchanged from the 2026-06-22 design.
