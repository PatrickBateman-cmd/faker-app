# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

See **[ARCHITECTURE.md](./ARCHITECTURE.md)** for Mermaid diagrams covering system architecture, all data flow pipelines, and the full database schema.

## Commands

### Backend (Python / uv)
```bash
cd backend
uv sync                                                              # Install / sync dependencies
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000             # Start dev server
uv run uvicorn app.main:app --reload --port 8000                    # Dev with hot-reload
uv sync --extra dev && uv run pytest tests/ -v                       # Install test deps + run all 40 backend tests
uv run pytest tests/test_foo.py::test_name                          # Single test
uv run faker --help                                                  # CLI entry point
uv run faker init                                                    # Init DuckDB (first run)
uv run faker info                                                    # DB stats
npx tsc --noEmit                                                     # TypeScript typecheck (frontend)
```

### Frontend (Node / npm)
```bash
cd frontend
npm install                  # Install dependencies
npm run dev                  # Start Vite dev server on :5173
npm run test                 # Vitest unit tests (2 tests)
npm run build                # tsc -b && vite build
```

### TUI (terminal UI — must stop server first)
```bash
cd backend
pkill -f uvicorn 2>/dev/null   # DuckDB single-writer: stop server before TUI
uv run faker tui
```

TUI controls: number keys `1`–`6` switch screens; field editor uses vim keys (`j`/`k` navigate, `J`/`K` reorder, `o`/`O` insert, `Delete` remove, `i` edit, `Esc`/`Enter` leave).

### Docker
```bash
docker compose up --build    # Backend on :8000, frontend on :80
docker compose down
```

## Architecture

### Stack
- **Backend**: Python 3.14, FastAPI, DuckDB (embedded OLAP), Pydantic-settings, Faker, yfinance, lxml, defusedxml, kaggle SDK, Textual (TUI), Typer (CLI)
- **Frontend**: React 19, Vite 6, Tailwind CSS v4, TanStack Query, React Router 7, Recharts, @dnd-kit

### Backend layout
```
backend/app/
  main.py          – FastAPI app: lifespan startup (DuckDB init + migrations + httpx shutdown), CORS, 9 routers, global exception handler
  config.py        – Settings via pydantic-settings; reads .env at repo root (Path(__file__).parent.parent.parent / ".env")
  core/
    database.py    – Thread-safe DuckDB singleton (DuckDBManager.get_instance()); RLock on execute + transaction()
    migrations.py  – Versioned SQL migrations; auto-run on startup; currently 6 migrations
    validation.py  – validate_column_name() / validate_table_name() — must use before any SQL interpolation
  routers/         – Thin HTTP layer; one APIRouter per domain
  schemas/         – Pydantic request/response models
  services/        – Business logic; routers → services → DuckDBManager
  templates/       – XML dataset templates (13 files) parsed with defusedxml
cli/               – Typer CLI (8 command groups); calls services directly, no HTTP
tui/               – Textual TUI (6 screens); calls services directly, no HTTP
```

Layering: **routers → services → DuckDBManager**. Never call DuckDBManager directly from routers.

### DuckDB conventions
- Every dataset gets a table named `dataset_{uuid4}`. Always double-quote in SQL: `"dataset_..."`.
- Metadata tables: `metadata_datasets`, `metadata_templates`, `metadata_runs`, `metadata_aggregations`, `metadata_iso_cache`.
- Two sequences: `seq_run_id` (runs) and `seq_aggregation_id` (aggregations/dedup). **Do not mix them** — aggregation INSERTs must use `nextval('seq_aggregation_id')` explicitly.
- Dataset tables are **immutable snapshots** — never updated after creation. Aggregation/dedup always creates a new table.
- Schema changes go through `migrations.py` — add a `Migration` entry with a monotonically increasing key. Each migration runs inside `BEGIN`/`COMMIT`/`ROLLBACK`; partial failures roll back atomically.
- All migrations use `IF NOT EXISTS` (idempotent), and the applied-marker is written inside the same transaction.
- Use `read_csv_auto(?, normalize_names=true, ignore_errors=true)` for CSV ingestion (Kaggle import). Use parameterized `LIMIT ?` — never interpolate `LIMIT {n}`.
- Batch inserts use `db.executemany(sql, batch)` — never row-by-row `execute()` in a loop.
- `zip(columns, row, strict=True)` in dataset_service.py — will error loudly on schema mismatch.
- Deleting a dataset also cascades to `metadata_aggregations` (via `delete_dataset` in dataset_service.py).

### DuckDBManager.transaction()
For multi-statement atomic blocks, use `db.transaction()` which holds the `RLock` for the entire block and wraps in `BEGIN`/`COMMIT`/`ROLLBACK`. Calling `db.execute()` inside is safe because `RLock` is reentrant:

```python
with db.transaction():
    db.execute("DELETE FROM metadata_templates")
    for t in templates:
        db.execute("INSERT INTO metadata_templates ...", [...])
```

Do **not** call `db.execute("BEGIN")` manually — use this context manager instead.

### Field type mapping (FieldDefinition → DuckDB)
| `type` value | DuckDB column type |
|---|---|
| `integer` | BIGINT |
| `float` / `decimal` | DOUBLE |
| `boolean` | BOOLEAN |
| `date` | DATE |
| `datetime` / `timestamp` | TIMESTAMP |
| anything else | VARCHAR |

### Template XML schema
```xml
<template name="Customer" category="E-Commerce">
  <meta description="Standard customer profile" version="1.0"/>
  <field name="id" type="integer" generator="uuid_int" unique="true"/>
  <field name="email" type="string" generator="formula"
         formula="{{first_name|lower}}.{{last_name|lower}}@company.com"/>
  <field name="age" type="integer" generator="random_int">
    <constraint min="18" max="99"/>
  </field>
  <field name="status" type="string" generator="random_element">
    <constraint values="active,pending,closed" weights="60,30,10"/>
  </field>
  <field name="signup_date" type="date" generator="date_between">
    <constraint start="-5y" end="today"/>
  </field>
</template>
```

- `constraint values` is a **comma-separated string**, not a list — `"active,pending,closed"`.
- `formula` fields use Jinja2 syntax; they may only reference fields that appear **earlier** in the field list.
- `condition: "age >= 18"` on a field skips it when the condition is false.
- `null_probability: 0.05` causes ~5% of values to be NULL.
- **Template names** must match `^[a-zA-Z0-9][a-zA-Z0-9 ._\-]{0,79}$` — enforced by `_template_path()` in `template_library.py`. Names are slugified to `[a-z0-9_]` for the filename; the name in the XML `name=` attribute is the canonical identifier.
- Do **not** bypass `_template_path()` when writing template files — it validates the name and confines the path to `TEMPLATES_DIR`.

### Generation engine — homogeneity
Homogeneity (1–100%) controls seed determinism:
- **100%**: every column gets the master seed → same value every row (fully deterministic).
- **50%**: ~50% of columns get the master seed, rest randomize per-row.
- **1%**: all columns randomize per row → different data on every run.

### Parent-child grouped generation
`--groups N` distributes rows across N parent groups. Parent fields repeat on every child row, identified by `parent_id`. `--split-pct P` controls what % of rows are grouped (rest have `parent_id=NULL`).

```bash
uv run faker generate --name "trades" --rows 1000 --groups 4 --split-pct 80 \
  --parent-fields-json '[{"name":"trade_id","generator":"uuid4","type":"string"}]' \
  --child-fields-json '[{"name":"qty","generator":"random_int","type":"integer","constraint":{"min":10,"max":1000}}]'
```

### Frontend layout
```
frontend/src/
  App.tsx          – Router, layout, toast context, template→generation navigation
  api/             – One file per domain; all calls go through /api/* (Vite proxies to :8000, strips /api prefix)
  types/           – TypeScript interfaces mirroring backend Pydantic schemas
  components/      – One dir per feature: <Name>/<Name>.tsx with named export
  hooks/           – useToast (global toast context replaces alert())
```

Routing: react-router-dom `<Routes>` + `<Route>`. 7 pages: `/`, `/templates`, `/iso20022`, `/financial`, `/kaggle`, `/generation`, `/datasets`, `/datasets/:id`. React Query `refetchInterval: 30000` with background refetch disabled.

### ISO 20022 integration
- Domains/messages scraped live from `iso20022.org`; XSDs cached in DuckDB with 1h TTL (`metadata_iso_cache`).
- `search_messages()` uses fallback hardcoded data first (instant), then checks cache — never blocks on live fetch for search.
- **"Save as Template" flow**: frontend flattens nested `ParsedField[]` with dot notation, maps `xsd_type` → `type` heuristically (`decimal|amount|price|rate` → `float`, `numeric|integer|year|index` → `integer`, else `string`), constructs XML, calls `POST /api/templates`. Duplicate saves return HTTP 409.
- XSD type mapping quirks: `ActiveCurrencyCode` → `string` (not `float`), `CountryCode` → `string` (not `integer`).
- **XSD fetching is SSRF-protected**: `_fetch_xsd()` validates `urlparse(url).netloc` against `{www.iso20022.org, iso20022.org}` before fetching. Only add to `_ALLOWED_XSD_HOSTS` if the new host is a trusted ISO 20022 schema source.
- The module-level `httpx.Client` is closed during FastAPI lifespan shutdown via `iso20022_service.close_client()`. If you add other persistent HTTP clients elsewhere, wire them to the lifespan the same way.

### Kaggle integration
- `backend/app/services/kaggle_service.py` uses the official `kaggle` Python package (≥1.6.0, resolves to 2.x with kagglesdk).
- `_setup_env()` pushes credentials into env vars before the package reads them.
- kaggle 2.x (kagglesdk) uses **snake_case** attributes: `dataset_files`, `total_bytes`, `creation_date` — not camelCase.
- KGAT_ bearer tokens go in `KAGGLE_API_TOKEN`; legacy auth uses `KAGGLE_USERNAME` + `KAGGLE_KEY`.
- Import tries single-file download first; falls back to full dataset zip + extract.
- `max_rows` in `_ingest_csv` is passed as a parameterized `LIMIT ?` — never string-interpolated. Must be a positive integer.
- Frontend `KagglePanel`: pasting a full `kaggle.com/datasets/owner/slug` URL skips search and goes directly to the file browser.

### TUI conventions
- Use `switch_screen` (not `push_screen`) to avoid stacking duplicate screens.
- Catppuccin Mocha theme in `tui/app.tcss`; loaded via `CSS_PATH = "app.tcss"` on the App class.
- Custom widget classes (`FieldList`, `DatasetTable`, `FieldRow`) must forward `**kwargs` to `super().__init__()`.
- TUI calls backend services directly in-process — no HTTP server.
- **Must stop FastAPI server before running TUI** (DuckDB single-writer lock).

## API endpoints reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/generate` | Generate 1–4 datasets |
| `GET` | `/datasets` | List datasets |
| `GET` | `/datasets/{id}/rows?page=1&per_page=100` | Paginated rows |
| `GET` | `/datasets/{id}/columns` | Column names |
| `PATCH` | `/datasets/{id}/rename` | Rename dataset |
| `DELETE` | `/datasets/{id}` | Drop table |
| `GET` | `/datasets/{id}/export/{csv\|parquet\|xlsx\|jsonl}` | Download |
| `POST` | `/datasets/{id}/aggregate` | GROUP BY → new snapshot |
| `POST` | `/datasets/{id}/dedup` | ROW_NUMBER() dedup → new snapshot |
| `GET` | `/templates` | List templates |
| `POST` | `/templates` | Create from XML |
| `DELETE` | `/templates/{name}` | Delete |
| `GET` | `/financial/quote?ticker=AAPL` | Real-time quote |
| `GET` | `/financial/history?ticker=AAPL&period=1mo&interval=1d` | Historical OHLCV |
| `POST` | `/financial/batch-to-dataset` | Batch quotes → DuckDB dataset |
| `POST` | `/financial/batch-history` | Batch history → DuckDB dataset |
| `POST` | `/financial/enrich` | Enrich dataset with yfinance data |
| `GET` | `/iso20022/domains` | List business domains |
| `GET` | `/iso20022/search?q=pacs` | Search messages |
| `GET` | `/iso20022/messages/{id}/xsd` | Parse XSD into template fields |
| `POST` | `/iso20022/messages/{id}/save-template` | Save as XML template |
| `GET` | `/kaggle/credentials` | Check if credentials configured |
| `GET` | `/kaggle/search?q=...` | Search Kaggle datasets |
| `GET` | `/kaggle/datasets/{owner}/{slug}/files` | List CSV files |
| `POST` | `/kaggle/import` | Download and ingest CSV into DuckDB |
| `GET` | `/health` | Health check |
| `GET` | `/info` | DB stats |

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `AUTH_ENABLED` | `false` | JWT auth toggle — **declared but not implemented** |
| `DUCKDB_PATH` | `./duckdb` | Database directory |
| `CORS_ORIGINS` | `http://localhost:5173` | Allowed origins |
| `JWT_SECRET` | `change-me` | JWT signing key (when auth implemented) |
| `JWT_EXPIRY_HOURS` | `24` | Token expiry |
| `YFINANCE_CACHE_TTL_QUOTES` | `30` | Quote cache TTL (seconds) |
| `YFINANCE_CACHE_TTL_HISTORICAL` | `3600` | Historical data cache TTL |
| `ISO20022_CACHE_TTL` | `3600` | ISO catalog cache TTL |
| `MAX_ROWS_PER_DATASET` | `100000` | Row cap per dataset |
| `MAX_DATASETS_PER_RUN` | `4` | Batch size cap |
| `KAGGLE_API_TOKEN` | `""` | KGAT_ bearer token |
| `KAGGLE_USERNAME` / `KAGGLE_KEY` | `""` | Legacy Kaggle auth |

## Gotchas

- **Cold start**: yfinance takes ~5s to import on first backend startup.
- **DuckDB single-writer**: can't query the `.duckdb` file while the server runs. Must stop the server to run the TUI or direct CLI queries.
- **`.env` location**: config.py reads `.env` from the **repo root** (`faker-app/.env`), not from `backend/`.
- **`faker` script path**: `.venv/bin/faker` inserts `backend/` into `sys.path` via a generated `.pth` workaround; regenerated by `uv sync` and is in `.gitignore`.
- **Tailwind v4 import order**: `@import` for Google Fonts must come **before** `@import "tailwindcss"` in `index.css`.
- **ISO 20022 offline**: falls back to hardcoded domain/message list when `iso20022.org` is unreachable.
- **Auth middleware**: `AUTH_ENABLED` and JWT settings exist in `config.py` but the middleware is not wired up — all endpoints are currently public.
- **Export temp files**: server-side temp files are named with `secrets.token_hex(16)` (not the dataset name). Cleaned up via `BackgroundTasks` after response — do not delete them manually mid-request. The friendly download name is passed separately to `FileResponse(filename=...)`.
- **CORS multi-origin**: `CORS_ORIGINS` is a comma-separated string; each entry is `.strip()`-ed before use. A trailing space in the env var will no longer silently break a listed origin.
- **RLock re-entrance**: `DuckDBManager._lock` is a `threading.RLock` (not `Lock`). This is intentional — `transaction()` holds the lock while inner `execute()` calls re-acquire it. Do not change it back to `Lock`.

## Security model (as of June 2026)

The following security controls are in place:

| Area | Control |
|---|---|
| SQL identifiers | All table/column names validated via `validate_table_name()` / `validate_column_name()` before interpolation |
| SQL values | All user-supplied values passed as `?` parameters; `LIMIT` also parameterized |
| Template path | `_template_path()` validates name against regex and resolves+confines path to `TEMPLATES_DIR` |
| Export path | Temp files named with `secrets.token_hex(16)`; user-supplied name only used for the HTTP `Content-Disposition` header |
| XML parsing | `defusedxml.ElementTree` throughout (XXE-safe) |
| HTTP fetching | ISO 20022 XSD fetcher has host allowlist `{www.iso20022.org, iso20022.org}` |
| Thread safety | `DuckDBManager` uses `RLock`; multi-statement transactions use `db.transaction()` |
| CORS | Explicit method/header lists; origins parsed with `.strip()` |

**Not yet implemented**: `AUTH_ENABLED` / JWT middleware — all endpoints are currently public.

## Known open issues (as of June 2026)

- Auth (`AUTH_ENABLED`) declared but not implemented.
- Some XSD `<xs:include>` / `<xs:import>` directives ignored; nested types depth-limited (50 elements).
- No frontend test coverage beyond ThemeSwitcher smoke test.
- Financial panel does not cache historical data across page navigations.
- `enrich_dataset` loads full source table into Python memory for large datasets — DuckDB-native join not yet implemented.
- yfinance batch calls are sequential (one HTTP call per symbol) — no parallelism yet.

## Planned: Rust generation engine (MIGRATION.md)

The generation hot path (`_generate_field_value`) is planned to move to a Rust PyO3 extension (`faker_engine.so`) using `maturin`, `rayon` (parallel), and the `fake` crate. This would replace the inner loop in `generation_engine.py` with a call to `gen_rows()` while keeping all DuckDB + metadata logic in Python. **Not yet implemented.**
