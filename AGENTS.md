# Faker App — AGENTS.md

## Run

### Web UI (two terminals)

```sh
# Terminal 1 — Backend (port 8000)
cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# Terminal 2 — Frontend (port 5173)
cd frontend && npm run dev
```

Vite proxies `/api/*` → `http://localhost:8000/` (strips `/api` prefix).

### CLI (no server needed)

```sh
cd backend

# Init DuckDB (first time)
uv run faker init

# Generate 100 rows from a template
uv run faker generate --name "demo" --rows 100 --template Person

# List datasets
uv run faker datasets list

# View dataset rows
uv run faker datasets view <DATASET_ID> --page 1 --per-page 20

# Export to CSV
uv run faker datasets export <DATASET_ID> csv --output ./data.csv

# Batch financial quotes → dataset
uv run faker financial batch "AAPL,MSFT,GOOG" --name "tech_quotes"

# ISO search + save as template
uv run faker iso search pacs
uv run faker iso save-template pacs.008.001.12

# Aggregate a dataset
uv run faker transform aggregate <DATASET_ID> --name "by_country" --group-by "country" --agg "amount:sum:total"

# Deduplicate a dataset
uv run faker transform dedup <DATASET_ID> --name "unique" --keys "email"

# All commands support --format json and --db <path>
```

## Gotchas

- **Cold start**: yfinance takes ~5s to import. Wait after starting backend.
- **Stale DB**: delete `backend/duckdb/default_user.duckdb` when schemas change. No migration system.
- **No test suite exists**. `pytest` is an optional dev dep only.
- **Frontend routing**: `useState<Page>` in `App.tsx`, no react-router. Add page as string literal to `Page` type + conditional render.
- **No auth middleware**. All endpoints public. `AUTH_ENABLED` setting is declared but unimplemented.

## Architecture

```
backend/cli/main.py              ← typer CLI entry point (8 command groups)
backend/cli/common.py            ← Shared CLI state, DuckDB init, output helpers
backend/cli/*.py                 ← Command groups: generate, datasets, templates, iso, financial, transform
backend/app/main.py              ← FastAPI entry, registers 8 routers, global exception handler
backend/app/core/database.py     ← DuckDBManager singleton (thread-safe via Lock)
backend/app/core/validation.py   ← validate_column_name() / validate_table_name()
backend/app/config.py            ← Pydantic Settings from .env at repo root
backend/app/routers/*.py         ← Each = APIRouter(prefix=..., tags=...)
backend/app/services/*.py        ← Business logic
backend/app/schemas/*.py         ← Pydantic models
```

Key service files: `generation_engine.py`, `dataset_service.py`, `transform_service.py` (aggregation+dedup), `export_service.py`, `template_library.py`, `iso20022_service.py`, `financial_service.py`.

## Backend conventions

- DuckDBManager singleton — uses `threading.Lock` around `execute()` and `initialize()`. Use `db.get_connection().executemany(sql, batch)` for batch inserts.
- Table names: `dataset_{8char_uuid}`. All table/column names are validated via `app.core.validation` before SQL interpolation.
- Field `type` in FieldDefinition maps: `integer`→BIGINT, `float`/`decimal`→DOUBLE, `boolean`→BOOLEAN, `date`→DATE, `datetime`/`timestamp`→TIMESTAMP, else VARCHAR.
- `ConstraintConfig.values` is a **comma-separated string**, not a list.
- Routers use `except ValueError` for 404s, broad `except Exception` for 500s. A global exception handler in `main.py` catches all unhandled errors returning 500.
- Export temp files are cleaned up via `BackgroundTasks` after response.
- `zip(columns, row, strict=True)` in `dataset_service.py` — will error loudly on schema mismatch.

## Frontend conventions

```sh
npx tsc --noEmit                                  # typecheck only
npm run build   # tsc -b && vite build            # full build
```

- Components live in `src/components/<Name>/<Name>.tsx` with named exports.
- API calls in `src/api/<name>.ts` using `fetch()` to `/api/*`.
- Types in `src/types/<name>.ts`.
- React Query (`@tanstack/react-query`) for server state. `refetchInterval: 30000` in ResultsViewer.
- Charting: Recharts (line chart in FinancialPanel).
- Dataset list auto-refetches every 30s (background refetching disabled).

## Refactoring completed (June 2026)

Phases 1–4 are done. See `REFACTOR.md` for full details.

| Area | What was fixed |
|---|---|
| **SQL injection** | All 13+ f-string SQL spots now validate table names (`^dataset_[a-f0-9-]+$`) and column names (`^[a-zA-Z_][a-zA-Z0-9_]*$`) |
| **Thread safety** | `threading.Lock` on DuckDBManager execute/initialize/close |
| **Batch INSERT** | `executemany` replaces row-by-row loop (20x fewer round-trips) |
| **XXE** | `defusedxml.ElementTree` replaces `xml.etree.ElementTree` |
| **Path traversal** | Filenames sanitized, `os.path.basename` used |
| **Temp file leak** | `BackgroundTasks` cleanup after export response |
| **Open endpoint** | `/datasets/table/{name}/rows` removed |
| **Bare excepts** | Caught specific types, exceptions logged |
| **httpx pool** | Single reused `httpx.Client` instead of per-request instances |
| **`lru_cache` cleared** | `_cache_clear()` call removed from XSD parse path |
| **`import random` loop** | Moved to module top |
| **Dead code** | `_SHARED_KEY_CACHE` removed |
| **Transaction** | Template metadata sync wrapped in `BEGIN/COMMIT` |
| **Global error handler** | Catches all unhandled exceptions, logs, returns 500 |
| **Frontend refetch** | Changed from 5s to 30s, background refetch disabled |
| **Full UUIDs** | 8-char truncation removed, full 36-char UUIDs for dataset IDs |
| **Export dropdown** | Hover → click-based toggle |
| **Duplicated types** | `types/generation.ts` imports and re-exports from `types/template.ts` |
| **Apply button** | TemplateLibrary Apply navigates to Generation with template loaded |
| **Unused imports** | `useEffect` removed from AggregationPanel |
| **Typed onResult** | `(result: unknown)` → `TransformResponse` type |
| **Delete error UI** | `onError` handler with `alert()` added |
| **Financial auto-fetch** | Default symbol removed, gated behind Search click |
| **Health degraded** | Returns degraded status if DuckDB is down |

## Remaining known issues

- Export dropdown click toggle could be improved (closes on blur with 200ms delay)
- Financial panel interval is hardcoded to 1d (no UI to change)
- Auth settings declared but not implemented

## Feature plan (appended June 2026)

### ISO 20022 Search
- `GET /iso20022/search?q=...` searches across all messages by short code (message_id) or full name (message_name)
- Backend: `search_messages(q)` in `iso20022_service.py` — fetches all domains' messages, filters case-insensitive substring match
- Frontend: Search input in `Iso20022Panel.tsx` with 300ms debounce, results shown in message column, ✕ to clear
- API function: `searchMessages(q)` in `api/iso20022.ts`

### Financial Batch → Dataset
- `POST /financial/batch-to-dataset` accepts `{"symbols": [...], "name": "..."}` (max 50 symbols)
- Backend: `batch_to_dataset()` in `financial_service.py` — fetches quotes for all symbols, creates DuckDB table, registers in metadata_datasets
- Frontend: Batch textarea + "Fetch & Save" button in `FinancialPanel.tsx`, result links to Datasets page
- Dataset columns: `symbol, shortName, longName, regularMarketPrice, previousClose, change, changePercent, dayHigh, dayLow, volume, marketCap, currency`
- Works with existing ResultsViewer (view, export, aggregate, dedup)

### Catppuccin Theme + JetBrains Mono
- 4 Catppuccin variants: Mocha (default dark), Macchiato, Frappé, Latte
- CSS custom properties in `index.css` for `--bg`, `--surface`, `--elevated`, `--border`, `--text`, `--muted`, `--accent`, `--green`, `--red`, `--selection`
- `ThemeSwitcher` component renders in sidebar, persists to localStorage
- All components use `bg-[var(--...)]` / `text-[var(--...)]` etc.
- JetBrains Mono loaded via Google Fonts, set as `font-family` on `:root`

### ISO → Template ("Save as Template")
- "Save as Template" button in `Iso20022Panel` XSD detail area (right column)
- On click: flattens `ParsedField[]` with `parent.child` dot notation for nested fields, maps `xsd_type` → `type` (decimal→float, integer→integer, date→date, boolean→boolean, else string), places `enumeration_values` into `<constraint values="..."/>`
- Constructs XML with `template name="{messageId} - {messageName}" category="ISO 20022"` and calls `POST /templates`
- On success, calls `onApply(templateName)` → user lands on Generation page with all ISO-derived fields pre-loaded
- Template persists in `backend/app/templates/*.xml`, appears in Template Library on future visits
- Creating the same ISO template twice returns HTTP 409 (Conflict)
- Uses `createTemplate()` from `api/templates.ts`; `onApply` prop added to `Iso20022Panel` in `App.tsx`

### Theme Switcher (rendering fix)
- `ThemeSwitcher` component existed but was never imported/rendered — added `import` + `<ThemeSwitcher />` inside `<aside>` sidebar after navigation in `App.tsx`
