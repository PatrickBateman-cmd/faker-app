# Collapsible/Reorderable Sections + Same-Generation Clue

**Date:** 2026-08-31
**Status:** Approved
**Scope:** Frontend (Generation view, Dataset view) + small backend field exposure (`run_id`)

---

## Part 1 — Collapsible, reorderable sections

### Generation view (`GenerationControls.tsx`)

The 1–4 per-dataset config panels (name / rows / group-config / fields) become
collapsible, drag-reorderable cards.

- New shared component `components/CollapsibleSection/CollapsibleSection.tsx`:
  a card with a header (drag handle `⠿`, title, collapse chevron) wrapping
  `children`. Built with `useSortable`, same dnd-kit pattern already used for
  `SortableFieldRow`.
- Each dataset panel is wrapped in `<CollapsibleSection>`. Collapsed state is
  local component state (a `Set<number>` of collapsed dataset indices).
- The `datasets.map(...)` block is wrapped in a `DndContext` /
  `SortableContext`; drag-end reorders the `datasets` array with `arrayMove`,
  mirroring the existing `moveField` logic.
- Reordering datasets is purely cosmetic — nothing references a dataset by
  array position (no `shared_key` UI is wired up yet), so this is safe.

### Dataset view (`ResultsViewer.tsx`, `/datasets/:id`)

The four currently-mutually-exclusive tabs (Data / Chart / Aggregate / Dedup)
become independent collapsible accordion sections:

- Replace the single `mode` state with an ordered array of section keys
  (`["data", "chart", "aggregate", "dedup"]`) held in state, plus a
  `collapsed: Set<string>`.
- Each section renders as a `CollapsibleSection`; content mounts (and
  fetches) only while expanded, so `DatasetChart`'s auto-fetch on mount does
  not fire until the user opens it.
- Drag-to-reorder uses the same `DndContext`/`arrayMove` pattern.
- `AggregationPanel`/`DedupPanel`'s `onBack` callback (previously "return to
  Data tab") becomes "collapse this section and invalidate the dataset list"
  since there's no more single active tab.

No persistence (localStorage, etc.) — plain React state, resets on
navigation/reload.

---

## Part 2 — "Same generation" display clue

**Goal:** when browsing datasets in the Dataset view's sidebar list, make it
visually obvious which datasets were produced by the same `POST /generate`
call (same `run_id`), since a single generation call can produce 1–4 datasets
that a user will often want to reason about together later.

### Backend

`metadata_datasets` already stores `run_id` (see `main.py` lifespan
migrations); it's just never selected out. Add `run_id` to the two read
paths in `dataset_service.py`:

- `list_datasets()`: add `run_id` to the `SELECT` and to the returned dict.
- `get_dataset()`: same.

No schema/migration change — the column already exists. No new Pydantic
model needed; both endpoints already return plain dicts.

### Frontend

- `types/dataset.ts`: add `run_id: number` to `DatasetMeta`.
- `ResultsViewer.tsx` sidebar list: badge each entry with `Run #<run_id>`,
  and visually group consecutive same-`run_id` entries (list is already
  `ORDER BY created_at DESC`, so datasets from one generation call are
  adjacent) with a shared accent-colored left border rather than a repeated
  per-row label, so grouping reads at a glance without repeating "Run #12"
  four times in a row.
- Detail pane header (`mode === "data"` block) also shows the `Run #<run_id>`
  badge next to the existing homogeneity/seed line.

---

## What is not changing

- No new DuckDB tables/migrations.
- No change to the generation engine's row-generation logic for Parts 1/2
  themselves. Note: `generation_engine.py` does change in this same working
  set, but for an unrelated, separately-designed reason — see
  [2026-08-31-grouped-dataset-overlap-design.md](./2026-08-31-grouped-dataset-overlap-design.md).
- Dataset ordering/pagination logic in `dataset_service.list_datasets` is
  unchanged beyond the added column.
