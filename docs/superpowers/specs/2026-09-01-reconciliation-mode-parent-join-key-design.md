# Reconciliation Mode — Parent-Level Join Key

**Date:** 2026-09-01
**Status:** Approved
**Scope:** Backend generation engine only (validation + a second, group-indexed pool). No new API fields, no CLI flags, one small frontend hint fix.
**Builds on:** [2026-09-01-reconciliation-mode-design.md](./2026-09-01-reconciliation-mode-design.md) (the `reconciliation_mode`/`field_breaks`/ground-truth feature this extends) and [2026-08-31-grouped-dataset-overlap-design.md](./2026-08-31-grouped-dataset-overlap-design.md) (the child-only pool restriction this partially relaxes).

---

## Overview

`reconciliation_mode`'s join key (`exact_fields[0]`) is currently restricted to child-level fields for grouped datasets — inherited unchanged from the pre-existing `overlap_ratio`/`exact_fields` mechanism, where that restriction was explicit and deliberate: parent fields already repeat identically across every child row *within one dataset's own groups*, so the row-indexed pool was never wired to inject into parent rows at all (`grouped.py`'s `_next_parent_row()` never receives a `pool_entry`; see `engine.py:59-67` for the validation that rejects any parent-field `exact_fields` entry today).

That reasoning doesn't hold for reconciliation mode's actual use case: matching the same natural business-key value — typically a **parent**-level field in a trade/transaction data model (e.g. `transaction_id`) — **across different datasets** in the same batch (GL vs sub-ledger, both modeled as transaction + line items). The current design has no mechanism for that at all: parent rows are generated fully independently per dataset, with no cross-dataset correspondence.

This spec adds that mechanism, scoped narrowly: **only the join key** (`exact_fields[0]`) may be parent-level, **only when every dataset in the batch is grouped**, matching **group-by-group** (group *i* in dataset A corresponds to group *i* in dataset B). Everything else — `field_breaks`, non-join-key `exact_fields`, the plain (non-reconciliation) `overlap_ratio` feature — is untouched.

**Explicitly out of scope** (may be revisited later, each as its own design): flat-vs-grouped reconciliation (one dataset flat, another grouped, reconciling on the flat dataset's row against the grouped dataset's group); parent-level fields other than the join key carrying their own `field_breaks`.

---

## Validation & Contract Changes (`engine.py`)

No new request/response fields — the change is entirely in what the existing `reconciliation_mode` + `exact_fields` combination is allowed to mean.

Today (`engine.py:55-71`), the overlap-validation block rejects *any* `exact_fields` entry that names a parent field, for *any* grouped dataset, unconditionally. That check must now be **conditional**: it still applies unconditionally to `exact_fields[1:]` (every entry after the join key), but `exact_fields[0]` gets a carve-out — parent-level is allowed for it, but only under all of the following, checked inside the existing `if request.reconciliation_mode:` block (`engine.py:29-53`), right after `join_key_field = request.exact_fields[0]` (`engine.py:37`):

| Condition | Check |
|---|---|
| Join key is parent-level on *some* dataset | `join_key_field` found in that dataset's `group_config.parent_fields` names |
| → then: every dataset must be grouped | `all(ds.group_config is not None for ds in request.datasets)` — reject with `ValueError` naming the offending flat dataset otherwise |
| → and: every dataset's join key must live in `parent_fields`, not `child_fields` | consistency — can't be parent-level on one dataset and child-level on another; reject otherwise |
| → and: every grouped dataset shares the same `num_groups` | required for group-index correspondence; reject otherwise |
| → and: every grouped dataset has `split_pct == 100` | excludes the mixed grouped+flat-row edge case for v1; reject otherwise |

When the join key is child-level (today's only supported case, and the common case for flat-vs-flat reconciliation), none of the above fires and behavior is byte-for-byte unchanged — including the existing per-entry check in the overlap-validation block (`engine.py:62-67`), which continues to run for `exact_fields[1:]` exactly as it does today, and for `exact_fields[0]` whenever it isn't parent-level.

---

## Parent Pool (`overlap.py`)

New function, alongside the existing `build_overlap_pool` (`overlap.py:15-28`):

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

One entry per **group index**, not per row — sized to `num_groups` directly (no separate ratio: `reconciliation_mode` already forces `overlap_ratio = 1.0`, i.e. full coverage, so there's no partial-pool case to support here).

In `engine.py`, built once (mirroring the existing pool-build block at `engine.py:77-84`) from `request.datasets[0].group_config.parent_fields` and `request.datasets[0].group_config.num_groups` — any dataset works since the validation above guarantees they all match — but **only** when the join-key-is-parent-level condition holds. When building the existing row-level `overlap_pool`, the join key field name is excluded from `exact_field_names` passed to `build_overlap_pool` in that case, since it's handled by the parent pool instead, not double-handled by both.

---

## Wiring (`grouped.py`)

`generate_grouped_dataset` (`grouped.py:22-30`) gains one new parameter: `parent_pool: list[dict] | None = None`.

`_next_parent_row()` (`grouped.py:113-118`) currently takes no arguments and is called from two places — the grouped loop (`grouped.py:123`, inside `for g_idx in range(num_groups):`) and the flat-rows loop (`grouped.py:147`, inside `for _ in range(flat_rows):`). It gains an optional `group_idx: int | None = None` parameter; the grouped-loop call site passes `g_idx`, the flat-rows call site passes nothing (stays `None` — moot in practice once `split_pct == 100` is required whenever a parent pool is in play, since that leaves `flat_rows == 0`, but the parameter stays optional so the function's contract doesn't silently assume that invariant). Inside `_next_parent_row()`, when `parent_pool` is provided and `group_idx is not None`, the corresponding `parent_pool[group_idx]` entry is merged into the `pool_entry` passed to `generate_row(parent_fields, ...)` the same way `sql_entry` already is (`grouped.py:116`) — giving every child row spawned from that parent group the same join-key value, and giving that value a real cross-dataset correspondence via the shared `parent_pool` built once in `engine.py`.

**Ground-truth `join_key_value` resolution** (`grouped.py:135` and `grouped.py:156`, both call sites of `apply_field_breaks`): today this always reads `child_row[join_key_col_idx]`, because the join key has only ever been a child field. It now needs to branch: if the join key lives in `parent_fields` (determined once, before the row loops, alongside the existing `join_key_col_idx` computation), read the value from `parent_row` at its position in `parent_fields` instead of from `child_row`. This is the only place the parent/child distinction leaks into the break-recording path — `field_breaks` themselves keep targeting child-level fields exclusively, unchanged.

Both call sites' existing guard, `if field_breaks and join_key_col_idx is not None:`, also needs updating — `join_key_col_idx` is `None` whenever the join key is parent-level (it's only ever resolved against `child_field_names`), so that guard would never fire for a parent-level join key even when child-level `field_breaks` are configured on other fields. Replace it with `if field_breaks and (join_key_in_parent or join_key_col_idx is not None):`, where `join_key_in_parent` is the same flag computed once before the row loops.

**Group-size determinism.** The existing per-group child-row distribution (`grouped.py:76-85`) draws `num_groups` random weights per dataset, so two datasets with the same `num_groups` will still, with near certainty, split their rows across groups differently (dataset A's group 0 might get 5 child rows while dataset B's group 0 gets 3). The row-level `overlap_pool` (used for any non-join-key `exact_fields`/`field_breaks`, e.g. an `amount` field) is consumed via a flat, monotonically-increasing `row_idx` counter — so with mismatched group sizes, "row 5" in dataset A and "row 5" in dataset B can fall in *different* transaction groups even though the join key itself still matches correctly group-by-group. A child-level break configured alongside a parent-level join key would then not reliably apply within the correct transaction.

Fix: `generate_grouped_dataset` gains a `deterministic_group_sizes: bool = False` parameter, set by `engine.py` to `join_key_is_parent`. When `True`, `group_sizes` is computed with an even split instead of random weights:

```python
if deterministic_group_sizes:
    base, remainder = divmod(grouped_rows, num_groups)
    group_sizes = [base + (1 if i < remainder else 0) for i in range(num_groups)]
    group_sizes = [max(1, s) for s in group_sizes]
else:
    # existing random-weighted logic, unchanged
    ...
```

Since parent-level join keys already require identical `num_groups`, identical `rows`, and `split_pct == 100` (so `grouped_rows` is identical too) across every dataset in the batch, this makes `group_sizes` — and therefore every group's row-index boundaries — identical across datasets whenever a parent-level join key is active. `row_idx` then naturally respects group boundaries with no other change needed. When `deterministic_group_sizes` is `False` (every existing call site, and any grouped dataset not using a parent-level join key), behavior is byte-for-byte unchanged. The same pre-existing over-generation edge case the random path already has (when `grouped_rows < num_groups`, `max(1, s)` can push `sum(group_sizes)` above `grouped_rows`) applies equally to the deterministic path — not a new limitation.

---

## Frontend (`GenerationControls.tsx`)

One fix: the inline red hint added in the previous session (flagging any typed `exact_fields` entry that's currently a parent field in a grouped dataset) currently applies to every entry, including position 0. It needs to exempt the join key once the backend allows it there — i.e., the check moves from "any typed field" to "any typed field *after* the first". Everything else (Field Breaks dropdown sourcing from `child_fields` only, since breaks stay child-only for v1) is unchanged.

No new UI surface — typing a parent field's name as the *first* Exact Fields entry becomes valid; typing one anywhere else still shows the existing warning.

---

## Error Handling

All new checks run inside the existing pre-DuckDB validation block in `engine.py`, consistent with the project's validate-before-touching-DuckDB convention (no partial-state cleanup needed). New `ValueError` messages, each naming the offending dataset/field:

- Join key is parent-level on one dataset but that dataset's `group_config` says it's a child field elsewhere, or a required dataset is flat: `"reconciliation_mode: parent-level join key 'X' requires every dataset to be grouped with 'X' as a parent field"`
- `num_groups` mismatch: `"reconciliation_mode: parent-level join key requires all grouped datasets to declare the same num_groups"`
- `split_pct != 100` on any grouped dataset: `"reconciliation_mode: parent-level join key requires split_pct=100 on every grouped dataset"`

---

## Testing

- Schema/validation tests: each row of the Error Handling table above gets a test (mismatched parent/child designation, mismatched `num_groups`, `split_pct != 100`, a flat dataset mixed in).
- Engine test: two grouped datasets, same `num_groups`, join key (`exact_fields[0]`) is a parent field on both, one child-level `field_breaks` entry — assert the same set of join-key values appears in both datasets (one per group), and that the non-join-key break still fires and records correctly (proving the parent/child resolution split didn't regress the existing child-break path).
- Determinism test: same two-dataset setup — assert `group_sizes` (inferred by counting child rows per join-key value) is identical between the two datasets, proving the deterministic split actually aligns group boundaries across datasets (not just matching total counts).
- Regression: existing child-level-join-key tests (from the base reconciliation-mode plan) must continue to pass unchanged — this is purely additive to the validation branch, not a rewrite of it.

---

## What is not changing

- The plain (non-`reconciliation_mode`) `overlap_ratio`/`exact_fields` feature — parent fields remain unconditionally unsupported there, exactly as the 2026-08-31 design doc specifies.
- `field_breaks` — still child-level fields only; no parent-level break mechanism is introduced.
- Flat-vs-grouped reconciliation — out of scope; requires reinterpreting `rows` vs `num_groups` correspondence and is its own design if wanted later.
- CLI (`cli/generate.py`) — no new flags; the existing `--exact-fields`/`--reconciliation-mode` flags already carry whatever the backend now accepts.
