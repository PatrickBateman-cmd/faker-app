# Faker App — Feature Implementation Plan

## Phase 0 — Quick Wins (~3h)

### 0.1 Template caching (`template_library.py`) — ~1h

Add file-mtime based caching so XML templates aren't re-parsed from disk on every API call.

```python
# At module level:
import time
_cache: dict[str, tuple[float, list[Template]]] = {}

def _load_templates_from_disk() -> list[Template]:
    cache_key = str(TEMPLATES_DIR)
    try:
        mtime = os.path.getmtime(TEMPLATES_DIR)
    except OSError:
        mtime = 0
    cached = _cache.get(cache_key)
    if cached and cached[0] >= mtime:
        return cached[1]
    # ... existing parsing logic ...
    _cache[cache_key] = (mtime, templates)
    return templates
```

Files: `backend/app/services/template_library.py`

### 0.2 Toast notification system (frontend) — ~2h

Replace `alert()` calls with a toast notification system.

Create:
- `frontend/src/hooks/useToast.ts` — simple queue-based toast state
- `frontend/src/components/Toast/Toast.tsx` — renders toasts in top-right corner, auto-dismiss after 3s
- Mount in `App.tsx`
- Replace `alert()` in: `ResultsViewer.tsx`, `AggregationPanel.tsx`, `DedupPanel.tsx`

Files: `frontend/src/hooks/useToast.ts` (new), `frontend/src/components/Toast/Toast.tsx` (new), `frontend/src/App.tsx` (modify), `frontend/src/components/ResultsViewer/ResultsViewer.tsx` (modify), `frontend/src/components/AggregationPanel/AggregationPanel.tsx` (modify), `frontend/src/components/DedupPanel/DedupPanel.tsx` (modify)

---

## Phase 1 — Generator Engine Upgrades (~8h)

### 1.1 Formula evaluation (`generation_engine.py`) — ~4h

- Add `jinja2` dependency to `pyproject.toml`
- In `_generate_field_value`, when `gen == "formula"`, collect already-generated values from current row and render the formula template using Jinja2's `Template` class
- Update XML template examples to use formulas

Files: `backend/pyproject.toml`, `backend/app/services/generation_engine.py`, `backend/app/schemas/generation.py`, `backend/app/templates/person.xml`

### 1.2 Null probability (`generation_engine.py`) — ~2h

- Add optional `null_probability: float | None = None` to `FieldDefinition` schema
- In `_generate_field_value`, skip generation and return `None` if `random.random() < field.null_probability`
- Add `null_probability` to XML template parsing
- Add CLI `--null-probability` support
- Add frontend UI input in DataDefinitionPane

Files: `backend/app/schemas/generation.py`, `backend/app/services/generation_engine.py`, `backend/app/services/template_library.py`, `backend/app/schemas/template.py`, `backend/cli/generate.py`

### 1.3 Weighted random elements (`generation_engine.py`) — ~2h

- Add optional `weights: list[float] | None = None` to `ConstraintConfig`
- In `_generate_field_value`, when `gen == "random_element"` and `weights` provided, use `random.choices(values, weights=weights, k=1)[0]`
- Parse `weights` from comma-separated string in XML `constraint weights="10,30,50,10"`
- Add frontend UI for weight distribution per value

Files: `backend/app/schemas/generation.py`, `backend/app/services/generation_engine.py`, `backend/app/services/template_library.py`

---

## Phase 2 — Financial Enrich Endpoint (~5h)

### 2.1 Backend service + router — ~3h

Add `POST /financial/enrich` endpoint:
- Request: `{ source_dataset_id, ticker_column: str, enrichments: [{ field_name, source: "quote"|"info" }] }`
- Response: `TransformResponse` (new dataset with original + enriched columns)
- Service function reads unique tickers, fetches yfinance for each, creates new table

Files: `backend/app/services/financial_service.py`, `backend/app/routers/financial.py`, `backend/app/schemas/financial.py` (new)

### 2.2 Frontend enrich UI — ~2h

- Dataset selector, column picker, checkbox list for enrichments
- Show result link to datasets page

Files: `frontend/src/api/financial.ts`, `frontend/src/components/FinancialPanel/FinancialPanel.tsx`

---

## Phase 3 — Frontend UX (~8h)

### 3.1 Field reordering (drag & drop) — ~3h

- Add `@dnd-kit/core` + `@dnd-kit/sortable`
- Wrap field list in DndContext + SortableContext
- Each field row becomes a useSortable item with drag handle

Files: `frontend/package.json`, `frontend/src/components/GenerationControls/FieldsEditor.tsx` (new)

### 3.2 Financial interval selector UI — ~2h

- Period dropdown + Interval dropdown in FinancialPanel above the chart
- Pass params to the API call

Files: `frontend/src/components/FinancialPanel/FinancialPanel.tsx`

### 3.3 Dashboard redesign — ~3h

- Add `GET /info` endpoint returning dataset count, row count, template count, recent runs
- Replace health-check ping with real stats + quick-action buttons

Files: `backend/app/routers/health.py`, `frontend/src/App.tsx`

---

## Phase 4 — Testing (~10h)

### 4.1 Backend test suite — ~8h

Tests in `backend/tests/`:
- `conftest.py` — in-memory DuckDB fixture
- `test_health.py`, `test_generation.py`, `test_templates.py`, `test_iso20022.py`, `test_financial.py`, `test_transform.py`, `test_validation.py`

### 4.2 Frontend test suite — ~2h

- Add `vitest` + `@testing-library/react`
- Component smoke tests

---

## Phase 5 — Advanced Features (~14h)

### 5.1 Generic dataset charting — ~5h
### 5.2 Offline ISO catalog cache — ~3h
### 5.3 Conditional generation — ~6h

---

## Phase 6 — Infrastructure (~11h)

### 6.1 React-router integration — ~6h
### 6.2 Database migrations — ~5h

---

## Phase 7 — Polish (~5h)

Shell completion docs, JSON Lines export, dataset rename, CLI progress bars, Docker Compose.

---

## Execution Order

```
Phase 0 ─────────────────────────────── do first (parallel: 0.1 + 0.2)
  ↓
Phase 1 ── 1.2 + 1.3 (parallel) → 1.1
  ↓
Phase 2 ── 2.1 → 2.2
  ↓
Phase 3 ── 3.2 + 3.3 (parallel) → 3.1
  ↓
Phase 4 ─────────────────────────────── do after phases 0-3
  ↓
Phase 5 ── 5.1 + 5.2 (parallel) → 5.3
  ↓
Phase 6 ── 6.1 → 6.2
  ↓
Phase 7 ─────────────────────────────── overlaps with everything
```
