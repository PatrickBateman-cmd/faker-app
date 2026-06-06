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

### TUI (terminal UI)

```sh
cd backend
uv run faker tui
# Number keys or g+letter to navigate screens
# Vim keys (j/k/J/K/o/O/dd/i/Esc) in field editor
```

### CLI (no server needed)

```sh
cd backend

# Init DuckDB (first time)
uv run faker init

# Generate 100 rows from a template
uv run faker generate --name "demo" --rows 100 --template Person

# Generate parent-child grouped dataset (4 groups, 1000 child rows)
uv run faker generate --name "trades" --rows 1000 --groups 4 \
  --parent-fields-json '[{"name":"trade_id","generator":"uuid4","type":"string"}]' \
  --child-fields-json '[{"name":"alloc_id","generator":"uuid4","type":"string"},{"name":"qty","generator":"random_int","type":"integer","constraint":{"min":10,"max":1000}}]'

# List datasets
uv run faker datasets list

# View dataset rows
uv run faker datasets view <DATASET_ID> --page 1 --per-page 20

# Export to CSV
uv run faker datasets export <DATASET_ID> csv --output ./data.csv

# Export to JSON Lines
uv run faker datasets export <DATASET_ID> jsonl --output ./data.jsonl

# Rename a dataset
uv run faker datasets rename <DATASET_ID> --name "new_name"

# Batch financial quotes → dataset (snapshot: 1 row/symbol)
uv run faker financial batch "AAPL,MSFT,GOOG" --name "tech_quotes"

# Batch financial history → dataset (time series: many rows/symbol)
uv run faker financial batch "AAPL,MSFT" --history --period 1mo --interval 1d --name "tech_history"

# Enrich an existing dataset with financial data
uv run faker financial enrich <DATASET_ID> --ticker-column symbol --enrich price,volume,market_cap

# ISO search + save as template
uv run faker iso search pacs
uv run faker iso save-template pacs.008.001.12

# Aggregate a dataset
uv run faker transform aggregate <DATASET_ID> --name "by_country" --group-by "country" --agg "amount:sum:total"

# Deduplicate a dataset
uv run faker transform dedup <DATASET_ID> --name "unique" --keys "email"

# All commands support --format json and --db <path>
```

### Tests

```sh
cd backend && uv run pytest tests/ -v     # 40 backend tests
cd frontend && npx vitest run             # 2 frontend tests
```

## Gotchas

- **Cold start**: yfinance takes ~5s to import. Wait after starting backend.
- **No auth middleware**. All endpoints public. `AUTH_ENABLED` setting is declared but unimplemented.
- **DuckDB single-writer**: can't query the `.duckdb` file while the server runs.
- **Schema migrations**: handled automatically on startup by `app/core/migrations.py`. No manual `rm` needed.

## Architecture

```
backend/cli/main.py              ← typer CLI entry point (8 command groups)
backend/cli/common.py            ← Shared CLI state, DuckDB init, output helpers
backend/cli/*.py                 ← Command groups: generate, datasets, templates, iso, financial, transform
backend/app/main.py              ← FastAPI entry, registers routers, global exception handler
backend/app/core/database.py     ← DuckDBManager singleton (thread-safe via Lock)
backend/app/core/validation.py   ← validate_column_name() / validate_table_name()
backend/app/core/migrations.py   ← Schema migration system (4 migrations)
backend/app/config.py            ← Pydantic Settings from .env at repo root
backend/app/routers/*.py         ← Each = APIRouter(prefix=..., tags=...)
backend/app/services/*.py        ← Business logic
backend/app/schemas/*.py         ← Pydantic models
backend/tui/                     ← Textual TUI (6 screens, 2 widgets)
backend/tests/                   ← 40 pytest tests (8 test files + conftest)
backend/Dockerfile               ← Python 3.14-slim production image
frontend/Dockerfile              ← Multi-stage nginx production image
docker-compose.yml               ← Backend + Frontend services
```

Key service files: `generation_engine.py`, `dataset_service.py`, `transform_service.py` (aggregation+dedup), `export_service.py`, `template_library.py`, `iso20022_service.py`, `financial_service.py`.

## Backend conventions

- DuckDBManager singleton — uses `threading.Lock` around `execute()` and `initialize()`. Use `db.get_connection().executemany(sql, batch)` for batch inserts.
- Table names: `dataset_{uuid}`. All table/column names are validated via `app.core.validation` before SQL interpolation.
- Field `type` in FieldDefinition maps: `integer`→BIGINT, `float`/`decimal`→DOUBLE, `boolean`→BOOLEAN, `date`→DATE, `datetime`/`timestamp`→TIMESTAMP, else VARCHAR.
- `ConstraintConfig.values` is a **comma-separated string**, not a list.
- Routers use `except ValueError` for 404s, broad `except Exception` for 500s. A global exception handler in `main.py` catches all unhandled errors returning 500.
- Export temp files are cleaned up via `BackgroundTasks` after response.
- `zip(columns, row, strict=True)` in `dataset_service.py` — will error loudly on schema mismatch.
- Migrations auto-run on startup via `app/core/migrations.py`. Idempotent (`IF NOT EXISTS`).

## Frontend conventions

```sh
npx tsc --noEmit                                  # typecheck only
npm run build   # tsc -b && vite build            # full build
npm run test    # vitest run                       # frontend tests
```

- Components live in `src/components/<Name>/<Name>.tsx` with named exports.
- API calls in `src/api/<name>.ts` using `fetch()` to `/api/*`.
- Types in `src/types/<name>.ts`.
- React Query (`@tanstack/react-query`) for server state. `refetchInterval: 30000` in ResultsViewer.
- Charting: Recharts (line chart in FinancialPanel, bar/line/pie in DatasetChart).
- Dataset list auto-refetches every 30s (background refetching disabled).
- **Routing**: react-router-dom with `<Routes>` + `<Route>`. 6 pages: `/`, `/templates`, `/iso20022`, `/financial`, `/generation`, `/datasets`. No `useState<Page>`.
- **Toasts**: `useToast()` hook + `<ToastContainer>` component replaces `alert()` calls.

## Refactoring completed (June 2026)

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
| **Template caching** | File-mtime based cache in `template_library.py` |
| **Schema migrations** | Auto-run on startup, version-tracked in `metadata_schema_version` |

## Features implemented (July 2026)

| Feature | What |
|---|---|
| **Formula evaluation** | `generator="formula"` fields evaluate Jinja2 templates with cross-field references (e.g. `{{first_name|lower}}.{{last_name|lower}}@example.com`) |
| **Null probability** | Field-level `null_probability: 0.05` causes ~5% of values to be NULL |
| **Weighted random elements** | `constraint weights="10,30,50,10"` controls distribution in `random_element` |
| **Conditional generation** | `condition: "age >= 18"` skips fields when condition is false |
| **Financial enrich** | `POST /financial/enrich` joins yfinance data against existing datasets |
| **Offline ISO cache** | ISO domains/messages/XSDs cached in DuckDB (1h TTL) for offline browsing |
| **Dataset charting** | Bar/line/pie charts for any dataset's numeric columns |
| **Dataset rename** | `PATCH /datasets/{id}/rename` + CLI `faker datasets rename` |
| **JSON Lines export** | `jsonl` format alongside CSV/Parquet/XLSX |
| **Database migrations** | Auto-applied on startup, version-tracked |
| **Toast notifications** | Replace `alert()` with auto-dismissing toasts |
| **Dashboard redesign** | Stats cards + recent datasets + quick actions |
| **Field drag & drop** | Reorder fields in Data Definition Pane |
| **Financial interval selector** | Period + interval dropdowns in Financial Panel |
| **React-router** | URL-based navigation with `/datasets/:id` deep-linking |
| **Docker Compose** | Production deployment with nginx reverse proxy |
| **Backend test suite** | 40 pytest tests covering all services + API |
| **Frontend test suite** | 2 vitest smoke tests |
| **Parent-child grouped generation** | `--groups N` distributes rows randomly across N parent groups with `parent_id` column; `split_pct` controls % of rows in groups |

## Remaining known issues

- Auth settings declared but not implemented (`AUTH_ENABLED`, JWT middleware)
- Export dropdown click toggle closes on blur with 200ms delay
- Financial panel does not cache historical data across page navigations
- Some XSD `<xs:include>` / `<xs:import>` directives are ignored (nested types limited)
- No frontend test coverage for components beyond ThemeSwitcher
