# Faker App

Synthetic dataset generator with ISO 20022 integration, financial data, aggregation, dedup, and multi-format exports.

## Prerequisites

- Python 3.14+
- Node.js 20+
- `uv` (Python package manager) — `curl -LsSf https://astral.sh/uv/install.sh | sh`

## Setup

### 1. Backend

```sh
cd backend
uv sync                    # install Python dependencies
cp ../.env.example ../.env  # copy default config (already done)
```

### 2. Frontend

```sh
cd frontend
npm install                # install JS dependencies
```

## Run (two terminals)

**Terminal 1 — Backend (port 8000):**
```sh
cd backend
rm -f duckdb/default_user.duckdb   # clean slate if schema changed
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Terminal 2 — Frontend (port 5173):**
```sh
cd frontend
npm run dev
```

Open **http://localhost:5173** in a browser. Vite proxies `/api/*` → `http://localhost:8000` (strips `/api` prefix).

## Environment

`.env` in the repo root with dev defaults:

| Variable | Default | Description |
|---|---|---|
| `AUTH_ENABLED` | `false` | Toggle multi-user auth |
| `DUCKDB_PATH` | `./duckdb` | DuckDB storage directory |
| `CORS_ORIGINS` | `http://localhost:5173` | Allowed CORS origins |
| `YFINANCE_CACHE_TTL_QUOTES` | `30` | Quote cache TTL (seconds) |
| `YFINANCE_CACHE_TTL_HISTORICAL` | `3600` | Historical data cache TTL |
| `MAX_ROWS_PER_DATASET` | `100000` | Max rows per generated dataset |
| `MAX_DATASETS_PER_RUN` | `4` | Max datasets per generation |

## CLI (no server needed)

All backend features are available from the command line without starting the web server:

```sh
cd backend

uv run faker init                                              # Init DuckDB
uv run faker generate --name "demo" --rows 100 --template Person  # Generate
uv run faker datasets list                                     # List datasets
uv run faker datasets view <ID>                                # View rows
uv run faker datasets export <ID> csv -o data.csv              # Export
uv run faker iso search pacs                                   # ISO search
uv run faker financial quote AAPL                              # Stock quote
uv run faker financial batch "AAPL,MSFT,GOOG"                  # Batch → dataset
uv run faker transform aggregate <ID> --name "r" --group-by country --agg "amount:sum:total"  # Aggregate
uv run faker transform dedup <ID> --name "r" --keys email      # Deduplicate
```

Add `--format json` for JSON output, `--db <path>` for custom DuckDB path.

## Quick Test (Web UI)

## Notes

- **Cold start**: yfinance takes ~5s to import on first startup.
- **DuckDB**: single-writer lock, can't query the `.duckdb` file while the server runs.
- **Stale database**: if schemas change between versions, delete `backend/duckdb/default_user.duckdb` and restart.
- **ISO 20022**: when iso20022.org is unreachable, the app uses hardcoded fallback data (5 domains, 12 messages, 15 demo fields).
- **ISO → Template**: browse ISO messages in the ISO 20022 panel, click "Save as Template" to create a reusable XML template. The template appears in the Template Library and can be applied to Generation on future visits.
- **Theme**: 4 Catppuccin variants (Mocha/Macchiato/Frappé/Latte) via the ThemeSwitcher dropdown in the sidebar. Persisted to localStorage.
- **Financial batch**: enter multiple stock symbols in the Financial panel's textarea to fetch quotes and save them as a DuckDB dataset (viewable, exportable, aggregate-able).
