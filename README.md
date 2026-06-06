# Faker App

Synthetic dataset generator with ISO 20022 integration, financial data (yfinance), aggregation/dedup, multi-format exports, and a full CLI.

**Stack**: Python 3.14 / FastAPI / DuckDB / React 19 / Vite / Tailwind CSS v4 / Recharts / Catppuccin theme

## Features

- **Data Generation** — 1–4 datasets per run, configurable homogeneity (1–100%), deterministic seeds, 50+ Faker generators
- **Parent-child grouped generation** — `--groups N` distributes rows across parent groups; parent fields repeat on every child row
- **Formula evaluation** — Cross-field Jinja2 templates (`{{first_name|lower}}.{{last_name|lower}}@example.com`)
- **Conditional fields** — `condition: "age >= 18"` skips fields based on other column values
- **Null probability** — Per-field NULL injection for realistic missing data
- **Weighted random elements** — Distribution weights for enum-style fields
- **Template Library** — Reusable XML templates stored on disk, CRUD via API/CLI
- **ISO 20022 Integration** — Live catalog browser, XSD parser → Faker generator mapping, "Save as Template"
- **Financial Data** — Real-time quotes and historical data via Yahoo Finance (yfinance), batch-to-dataset, enrichment
- **Aggregation & Deduplication** — SQL-based GROUP BY and ROW_NUMBER() via DuckDB
- **CLI** — Full-featured command-line interface (typer) with rich tables, JSON output, progress bars
- **Exports** — CSV, Parquet, XLSX, JSON Lines
- **Database Migrations** — Auto-applied on startup, no manual `.duckdb` deletion needed
- **Catppuccin Theme** — 4 variants (Mocha/Macchiato/Frappé/Latte), persisted to localStorage
- **Dataset charting** — Bar/line/pie charts for any dataset's numeric columns
- **Docker Compose** — Production-ready deployment with nginx reverse proxy

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

## Run

### Web UI (two terminals)

**Terminal 1 — Backend (port 8000):**
```sh
cd backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Terminal 2 — Frontend (port 5173):**
```sh
cd frontend
npm run dev
```

Open **http://localhost:5173**. Vite proxies `/api/*` → `http://localhost:8000`.

### CLI (no server needed)

```sh
cd backend
uv run faker init                                              # Init DuckDB
uv run faker generate --name "demo" --rows 100 --template Person  # Generate
uv run faker datasets list                                     # List datasets
uv run faker datasets view <ID>                                # View rows
uv run faker datasets export <ID> csv -o data.csv              # Export
uv run faker iso search pacs                                   # ISO search
uv run faker generate --name "trades" --rows 1000 --groups 4 \ # Parent-child grouped
  --parent-fields-json '[{"name":"trade_id","generator":"uuid4","type":"string"}]' \
  --child-fields-json '[{"name":"qty","generator":"random_int","type":"integer","constraint":{"min":10,"max":1000}}]'
uv run faker financial quote AAPL                                   # Stock quote
uv run faker financial batch "AAPL,MSFT" --name snap                # Snapshot (1 row/symbol)
uv run faker financial batch "AAPL,MSFT" --history --period 1mo     # History (time series)
uv run faker financial enrich <ID> --ticker-column sym --enrich price,volume  # Enrich
uv run faker transform aggregate <ID> --name "r" --group-by country --agg "amount:sum:total"  # Aggregate
uv run faker transform dedup <ID> --name "r" --keys email      # Deduplicate
```

All CLI commands support `--format json` and `--db <path>`.

### Shell Completion

```sh
uv run faker --install-completion   # Install tab completion
uv run faker --show-completion      # Preview script
```

### Tests

```sh
cd backend && uv run pytest tests/ -v     # 40 backend tests
cd frontend && npx vitest run             # 2 frontend tests
```

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

## Docker

```sh
docker compose up --build
```

Backend on `http://localhost:8000`, frontend on `http://localhost:80`.

## Notes

- **Cold start**: yfinance takes ~5s to import on first startup.
- **DuckDB**: single-writer lock, can't query the `.duckdb` file while the server runs.
- **Schema migrations**: auto-applied on startup — no manual `rm duckdb/` needed.
- **ISO 20022**: offline-capable (cached in DuckDB with 1h TTL). When iso20022.org is unreachable, falls back to cached or hardcoded data.
- **Formula fields**: use Jinja2 syntax (`{{field_name|lower}}`) and reference fields that appear earlier in the field list.
- **Financial enrich**: joins yfinance quote data against an existing dataset on a ticker column, creating a new enriched dataset.
- **Parent-child grouped generation**: `--groups N --split-pct P` creates parent-child datasets. Parent fields repeat on every child row within a group, identified by `parent_id`. `split_pct` controls % of rows in groups (rest are flat with `parent_id=NULL`).
- **Catppuccin theme**: 4 variants via the ThemeSwitcher dropdown in the sidebar, persisted to localStorage.
- **No auth**: `AUTH_ENABLED` setting is declared but unimplemented — all endpoints are public.

## Quick Test (Web UI)

```sh
# Health
curl http://localhost:8000/health

# Generate 50 rows
curl -X POST http://localhost:8000/generate \
  -H 'Content-Type: application/json' \
  -d '{"datasets":[{"name":"demo","rows":50,"fields":[{"name":"name","generator":"name","type":"string"},{"name":"email","generator":"email","type":"string"}]}],"homogeneity":100,"seed":42}'

# List datasets
curl http://localhost:8000/datasets

# Export CSV (replace DATASET_ID)
curl http://localhost:8000/datasets/DATASET_ID/export/csv
```

See `CHEATSHEET.md` for the full command reference.
