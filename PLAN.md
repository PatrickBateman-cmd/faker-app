# Faker App — Fake Dataset Generator

## Overview

A full-stack web application (Python/FastAPI + React) for generating up to 4 synthetic datasets simultaneously. Features include:

- **Template Library** — Custom XML templates stored on disk, plus live ISO 20022 financial message templates fetched on demand
- **Data Definition Pane** — Interactive column editor with type/generator/constraint selection
- **Dataset Generation** — 1–4 datasets per run, configurable homogeneity (1–100%), deterministic seeds
- **Aggregation & Deduplication** — SQL-based GROUP BY and DISTINCT ON via DuckDB
- **Financial Data** — Real-time quotes and historical data via Yahoo Finance (yfinance)
- **Snapshots** — Generated data is materialized as DuckDB tables (never mutated after creation)
- **Exports** — CSV, JSON, Parquet, XLSX
- **Multi-User** — Toggle-enabled JWT auth layer (AUTH_ENABLED env var)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  React Frontend (Vite + TypeScript)                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐               │
│  │ Template │ │  Data    │ │  Generation  │               │
│  │ Library  │ │ Def. Pane│ │  Controls    │               │
│  └──────────┘ └──────────┘ └──────┬───────┘               │
│  ┌──────────┐ ┌──────────┐ ┌──────▼───────┐               │
│  │ ISO20022 │ │ Financial│ │   Results    │               │
│  │ Panel    │ │ Panel    │ │   Viewer     │               │
│  └──────────┘ └──────────┘ └──────────────┘               │
│  ┌──────────┐ ┌──────────┐                                   │
│  │ Agg./    │ │ Project  │                                   │
│  │ Dedup UI │ │ Dashboard│                                   │
│  └──────────┘ └──────────┘                                   │
└────────────────────────┬────────────────────────────────────┘
                         │ REST API (JSON)
┌────────────────────────▼────────────────────────────────────┐
│  FastAPI Backend                                             │
│  ┌──────────────────┐ ┌──────────────────┐                  │
│  │ Template Library │ │ ISO 20022 Service│                  │
│  │ (XML files)      │ │ (XSD fetcher +   │                  │
│  │                  │ │  parser)         │                  │
│  └──────────────────┘ └──────────────────┘                  │
│  ┌──────────────────┐ ┌──────────────────┐                  │
│  │ Generation Engine│ │ Financial Service│                  │
│  │ (Faker +         │ │ (yfinance)       │                  │
│  │  homogeneity)    │ │                  │                  │
│  └──────────────────┘ └──────────────────┘                  │
│  ┌──────────────────┐ ┌──────────────────┐                  │
│  │ Aggregation/Dedup│ │ Export Service   │                  │
│  │ (SQL on DuckDB)  │ │ (COPY TO +       │                  │
│  │                  │ │  pandas)         │                  │
│  └──────────────────┘ └──────────────────┘                  │
│  ┌────────────────────────────────────────┐                 │
│  │  DuckDB (embedded OLAP)                │                 │
│  │  - dataset_{uuid} tables (snapshots)   │                 │
│  │  - metadata tables (templates, runs)   │                 │
│  │  - per-user .duckdb files              │                 │
│  └────────────────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
faker-app/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                        # FastAPI app entry
│   │   ├── config.py                      # Settings: AUTH_ENABLED, DUCKDB_PATH, etc.
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py                    # Conditional on AUTH_ENABLED
│   │   │   ├── templates.py               # CRUD for XML templates
│   │   │   ├── generation.py              # Dataset generation
│   │   │   ├── datasets.py                # Snapshots, rows, delete
│   │   │   ├── aggregation.py             # Aggregation + dedup
│   │   │   ├── financial.py               # yfinance endpoints
│   │   │   └── iso20022.py                # ISO catalog + XSD endpoints
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── template_library.py        # XML template loader
│   │   │   ├── iso20022_service.py        # Catalog browser + XSD parser
│   │   │   ├── generation_engine.py       # Faker + homogeneity + multi-dataset
│   │   │   ├── aggregation_service.py
│   │   │   ├── dedup_service.py
│   │   │   ├── export_service.py          # COPY TO + pandas
│   │   │   ├── duckdb_manager.py          # Connection, table lifecycle
│   │   │   └── financial_service.py       # yfinance wrapper
│   │   ├── models/
│   │   │   └── metadata.py                # Pydantic models
│   │   ├── schemas/
│   │   │   ├── generation.py
│   │   │   ├── template.py
│   │   │   ├── aggregation.py
│   │   │   └── iso20022.py                # Response models
│   │   ├── templates/                     # Custom XML template files
│   │   │   ├── person.xml
│   │   │   ├── company.xml
│   │   │   ├── ecommerce_order.xml
│   │   │   └── financial_transaction.xml
│   │   ├── middleware/
│   │   │   └── auth.py                    # Conditional JWT
│   │   └── core/
│   │       └── database.py                # DuckDB setup
│   ├── requirements.txt
│   ├── Dockerfile
│   └── tests/
│       ├── test_generation.py
│       ├── test_templates.py
│       ├── test_aggregation.py
│       └── test_iso20022.py
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── DataDefinitionPane/        # Column editor grid
│   │   │   ├── TemplateLibrary/           # Custom XML templates
│   │   │   ├── Iso20022Panel/             # Catalog browser, XSD preview
│   │   │   ├── GenerationControls/        # Rows, datasets, homogeneity slider
│   │   │   ├── AggregationPanel/          # Group-by + function picker
│   │   │   ├── DedupPanel/                # Dedup column + strategy selector
│   │   │   ├── FinancialPanel/            # Ticker lookup + field mapping
│   │   │   ├── ResultsViewer/             # Paginated table + export buttons
│   │   │   ├── ThemeSwitcher/             # Catppuccin theme selector
│   │   │   ├── Login/                     # Login/Register (conditional)
│   │   │   └── Layout/                    # Sidebar, nav, user menu
│   │   ├── api/                           # Axios/fetch API client
│   │   ├── hooks/                         # React Query hooks
│   │   ├── types/                         # TypeScript interfaces
│   │   ├── context/                       # Auth context (conditional)
│   │   └── App.tsx
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
├── .env.example
├── docker-compose.yml
├── PLAN.md
└── GEMINI.md
```

---

## Template System

### 1. Custom XML Templates

Templates are XML files stored in `backend/app/templates/`. Each file defines a reusable schema for dataset generation.

**Example: `person.xml`**

```xml
<template name="Customer" category="E-Commerce">
  <meta description="Standard customer profile" version="1.0"/>
  <field name="id" type="integer" generator="uuid_int" unique="true"/>
  <field name="first_name" type="string" generator="first_name"/>
  <field name="last_name" type="string" generator="last_name"/>
  <field name="email" type="string" generator="formula"
         formula="{{first_name|lower}}.{{last_name|lower}}@company.com"/>
  <field name="age" type="integer" generator="random_int">
    <constraint min="18" max="99"/>
  </field>
  <field name="signup_date" type="date" generator="date_between">
    <constraint start="-5y" end="today"/>
  </field>
  <relationship type="one_to_many" source="id" target="orders"/>
</template>
```

- `generator` attribute maps to a Python Faker provider or a custom provider
- `formula` type uses Jinja2-like expressions referencing other field values
- Templates are loaded at startup, cached in DuckDB, and editable via the API
- Users can upload new XML templates via the UI or API

### 2. ISO 20022 Live Templates

The app integrates with the [ISO 20022 Message Definitions](https://www.iso20022.org/iso-20022-message-definitions) catalog to provide financial message templates on demand.

**How it works:**

1. **User browses the catalog** in the Iso20022Panel — domains (Payments, Securities, FX, Cards, Trade Finance), business areas, and message definitions are fetched live from `iso20022.org`
2. **User selects a message** — e.g. `pacs.008.001.12` (FIToFICustomerCreditTransfer)
3. **Backend fetches the XSD** from the ISO 20022 download URL
4. **XSD is parsed** using `lxml` — element names, types, cardinalities, enumerations, and documentation are extracted
5. **Fields are mapped to Faker providers** heuristically:

| XSD Element | XSD Type | Mapped Generator |
|---|---|---|
| `Amount` | `xsd:decimal` | `pydecimal` |
| `Currency` | `xsd:string` (enumeration) | `random_element(enum_values)` |
| `BIC` | `xsd:string` (pattern) | `swift_bic` |
| `PostalAddress` | complex type | nested address fields |
| `Country` | `xsd:string` (enum) | `country_code` |
| `DateTime` | `xsd:dateTime` | `date_time_between` |
| `Reference` | `xsd:string` (maxLength) | `bothify(???#???##)` |

6. **The parsed template populates the Data Definition Pane** — user can tweak, add/remove fields
7. **User generates data** — fake but structurally valid financial messages

**API Endpoints:**

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/iso20022/domains` | List business domains |
| `GET` | `/iso20022/messages?domain=payments` | List message definitions in a domain |
| `GET` | `/iso20022/search?q=credit` | Search all messages by ID or name (case-insensitive, 2+ chars) |
| `GET` | `/iso20022/messages/{message_id}/xsd` | Fetch and parse XSD into template |
| `POST` | `/iso20022/messages/{message_id}/generate` | Generate directly from ISO template |

**"Save as Template" flow:**

1. User browses ISO messages and views XSD fields in the detail panel
2. Clicks "Save as Template" button in the right column
3. Frontend flattens nested `ParsedField[]` using `parent.child` dot notation
4. Maps `xsd_type` → `type` via heuristic: `decimal|amount|price|rate` → `float`, `numeric|integer|year|index` → `integer`, `date|time|timestamp` → `date`, `boolean|indicator` → `boolean`, else `string`
5. Places `enumeration_values` into `<constraint values="..."/>`
6. Constructs XML with `template name="{messageId} - {messageName}" category="ISO 20022"`
7. Calls `POST /api/templates` — saved to `backend/app/templates/`, appears in Template Library
8. Auto-navigates to Generation page with fields pre-loaded (reuses `onApply`/`pendingTemplate` flow)
9. Creating the same ISO template twice returns HTTP 409 (Conflict)

**Caching:** XSDs are cached in memory with a 1-hour TTL to avoid repeated downloads.

---

## Data Generation Engine

### Homogeneity Slider (1–100%)

Controls **deterministic seed** behavior:

| Value | Behavior |
|---|---|
| **100%** | Every column uses the project's master seed. Re-running with the same seed + definition produces identical data. |
| **50%** | ~50% of columns use the master seed, the rest use random seeds. |
| **1%** | Every column uses a unique random seed. Data differs on every run. |

The percentage determines the probability that any given column receives the master seed vs. a random seed.

### Multi-Dataset Generation

- Generate **1–4 datasets** in a single request
- Each dataset can use a different template or the same template with different parameters
- Datasets can share a common key column for cross-dataset relationships (e.g. `customer_id` in both `customers` and `orders`)
- Each dataset is stored as a separate DuckDB table: `dataset_{uuid}`

### Generation Request

```json
{
  "seed": 42,
  "homogeneity": 75,
  "datasets": [
    {
      "name": "customers",
      "template": "Customer",
      "rows": 10000,
      "fields": [
        {"name": "first_name", "generator": "first_name"},
        {"name": "last_name", "generator": "last_name"},
        {"name": "age", "generator": "random_int", "constraints": {"min": 18, "max": 99}}
      ]
    },
    {
      "name": "orders",
      "template": null,
      "rows": 50000,
      "fields": [
        {"name": "order_id", "generator": "uuid"},
        {"name": "customer_id", "generator": "shared_key", "source_dataset": "customers", "source_field": "id"},
        {"name": "amount", "generator": "pydecimal", "constraints": {"min": 1, "max": 1000}}
      ]
    }
  ]
}
```

---

## DuckDB Storage

### Why DuckDB

- **Embedded** — no separate server process, runs in-process with Python
- **Analytical** — excellent for aggregation and bulk operations
- **Columnar** — efficient storage and querying of generated datasets
- **Fast exports** — `COPY table TO 'file.csv'` is extremely fast
- **Multiple readers** — supports concurrent read access

### Storage Layout

```
duckdb/
  default_user.duckdb/          # Single-user mode (AUTH_ENABLED=false)
  user_{uuid}.duckdb/           # Multi-user mode (AUTH_ENABLED=true)
```

### Tables

| Table Name | Contents | Created By |
|---|---|---|
| `metadata_templates` | Parsed XML templates (cache) | Template service |
| `metadata_runs` | Generation run metadata | Generation engine |
| `metadata_aggregations` | Aggregation/dedup run metadata | Aggregation service |
| `metadata_users` | User accounts (multi-user only) | Auth service |
| `dataset_{uuid}` | Generated data snapshot | Generation engine |
| `dataset_{uuid}_field_{name}` | Derived aggregation result | Aggregation/dedup service |

### Dataset Lifecycle

```
[Defined] → POST /generate → [Generating] → [dataset_{uuid} in DuckDB]
                                                ↓
                                     POST /aggregate → [dataset_{uuid}_agg_{...}]
                                     POST /dedup      → [dataset_{uuid}_dedup_{...}]
                                     GET /export/csv  → [File Download]
                                     DELETE           → [DROP TABLE]
```

Snapshot tables are **immutable** — once created, they are never modified. Aggregation and deduplication always create new snapshot tables.

---

## Aggregation & Deduplication

### Aggregation

SQL-based `GROUP BY` with configurable functions:

- `sum`, `avg`, `min`, `max`, `count`, `count_distinct`, `first`, `last`
- User selects group-by columns and aggregation columns
- Result is stored as a new snapshot table

**Request:**
```json
{
  "source_dataset": "dataset_abc123",
  "name": "revenue_by_country",
  "group_by": ["country"],
  "aggregations": [
    {"column": "amount", "function": "sum", "alias": "total_revenue"},
    {"column": "amount", "function": "avg", "alias": "avg_revenue"},
    {"column": "customer_id", "function": "count_distinct", "alias": "unique_customers"}
  ]
}
```

### Deduplication

SQL-based `ROW_NUMBER() OVER (PARTITION BY ...)`:

- User selects key column(s) for duplicate detection
- Strategies: `keep_first`, `keep_last`, `keep_none` (remove all duplicates)
- Result is stored as a new snapshot table

**Request:**
```json
{
  "source_dataset": "dataset_abc123",
  "name": "deduplicated_customers",
  "keys": ["email"],
  "strategy": "keep_first",
  "order_by": {"column": "created_at", "direction": "desc"}
}
```

---

## Financial Data Integration (yfinance)

### Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/financial/quote?ticker=AAPL` | Real-time quote (price, change, volume, market cap) |
| `GET` | `/financial/history?ticker=AAPL&period=1mo&interval=1d` | Historical OHLCV data |
| `POST` | `/financial/batch-to-dataset` | Fetch quotes for up to 50 symbols, save as a DuckDB dataset |
| `POST` | `/financial/enrich` | Enrich an existing dataset with financial data |

### Batch-to-Dataset Flow

1. User enters symbols (e.g., `AAPL, MSFT, GOOG`) in a textarea
2. Frontend calls `POST /financial/batch-to-dataset {"symbols": [...], "name": "..."}`
3. Backend fetches yfinance quotes for each symbol, creates a DuckDB table with 12 columns: `symbol, shortName, longName, regularMarketPrice, previousClose, change, changePercent, dayHigh, dayLow, volume, marketCap, currency`
4. Table is registered in `metadata_datasets` and works with all existing tools (view, export, aggregate, dedup)

### Enrichment Flow

1. User has a dataset with a `ticker` column
2. User calls `POST /financial/enrich`:
   ```json
   {
     "source_dataset": "dataset_abc123",
     "ticker_column": "symbol",
     "enrichments": [
       {"field": "current_price", "type": "quote"},
       {"field": "pe_ratio", "type": "info"}
     ]
   }
   ```
3. Backend queries yfinance for each unique ticker, joins results back
4. A new enriched snapshot table is created

---

## Multi-User Toggle

Controlled by `AUTH_ENABLED` environment variable.

### Single-User Mode (`AUTH_ENABLED=false`)

- No auth middleware loaded
- All requests auto-bound to `default_user`
- All templates and datasets visible
- Single `default_user.duckdb` file

### Multi-User Mode (`AUTH_ENABLED=true`)

- JWT auth middleware active
- `POST /auth/register` and `POST /auth/login` endpoints
- Passwords hashed with `bcrypt`
- JWT tokens with configurable expiry
- Users isolated:
  - Templates, datasets, and runs scoped by `user_id`
  - Each user gets their own `user_{uuid}.duckdb` file
  - API endpoints filter by `user_id` from JWT

### Auth Endpoints (only when enabled)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/register` | Create user account |
| `POST` | `/auth/login` | Authenticate, receive JWT |
| `GET` | `/auth/me` | Current user info |

---

## API Endpoints Summary

### Templates

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/templates` | List all templates |
| `GET` | `/templates/{name}` | Get template detail |
| `POST` | `/templates` | Upload new XML template |
| `PUT` | `/templates/{name}` | Update template |
| `DELETE` | `/templates/{name}` | Delete template |

### Generation

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/generate` | Generate 1–4 datasets |

### Datasets

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/datasets` | List past generation runs |
| `GET` | `/datasets/{id}` | Preview first 100 rows |
| `GET` | `/datasets/{id}/rows?page=1&per_page=100` | Paginated rows |
| `GET` | `/datasets/{id}/export/{format}` | Download (csv/json/xlsx/parquet) |
| `DELETE` | `/datasets/{id}` | Drop snapshot table |

### Aggregation & Dedup

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/datasets/{id}/aggregate` | Aggregate dataset |
| `POST` | `/datasets/{id}/dedup` | Deduplicate dataset |

### Financial

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/financial/quote?ticker=AAPL` | Real-time quote |
| `GET` | `/financial/history?ticker=AAPL&period=1mo&interval=1d` | Historical data |
| `POST` | `/financial/batch-to-dataset` | Batch fetch quotes → DuckDB dataset |
| `POST` | `/financial/enrich` | Enrich dataset with financial data |

### ISO 20022

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/iso20022/domains` | List business domains |
| `GET` | `/iso20022/messages?domain=payments` | List message definitions |
| `GET` | `/iso20022/search?q=credit` | Search messages by ID or name |
| `GET` | `/iso20022/messages/{message_id}/xsd` | Parse XSD into template |
| `POST` | `/iso20022/messages/{message_id}/generate` | Generate from ISO template |

---

## Implementation Phases

### Phase 1: Scaffold
- Monorepo layout with `backend/` and `frontend/`
- FastAPI skeleton with health endpoint
- React + Vite + TypeScript + TailwindCSS setup
- DuckDB connection manager
- Docker Compose (backend, frontend)
- `.env.example` with `AUTH_ENABLED=false`

### Phase 2: Custom XML Templates
- `template_library.py` — XML parser, file watcher, CRUD
- Placeholder XML templates (`person.xml`, `company.xml`, etc.)
- `templates.py` router — list, get, create, update, delete
- `TemplateLibrary` React component — browse, search, apply

### Phase 3: ISO 20022 Integration
- `iso20022_service.py` — catalog scraper, XSD downloader, parser
- `lxml`-based XSD to template conversion
- Heuristic Faker provider mapping
- `Iso20022Panel` React component — domain tree, message search, XSD preview

### Phase 4: Generation Engine
- Faker provider integration
- Homogeneity algorithm (seed distribution)
- Multi-dataset generation (1–4 parallel datasets)
- `POST /generate` endpoint
- `GenerationControls` React component — rows, datasets count, homogeneity slider

### Phase 5: DuckDB Snapshots
- Snapshot table creation with inferred schema
- Streaming INSERT for large datasets
- Paginated row retrieval (`LIMIT/OFFSET`)
- `GET /datasets`, `GET /datasets/{id}/rows`
- `ResultsViewer` React component — paginated table

### Phase 6: Aggregation & Dedup
- `aggregation_service.py` — dynamic GROUP BY SQL builder
- `dedup_service.py` — ROW_NUMBER() OVER (PARTITION BY) SQL builder
- `AggregationPanel` and `DedupPanel` React components
- Derived snapshot tables

### Phase 7: Financial (yfinance)
- `financial_service.py` — yfinance wrapper with caching
- `GET /financial/quote`, `GET /financial/history`
- `POST /financial/enrich` — enrich existing datasets
- `FinancialPanel` React component — ticker search, field mapping

### Phase 8: Exports
- `export_service.py` — COPY TO for CSV/Parquet, pandas for XLSX
- `GET /datasets/{id}/export/{format}` endpoints
- Download buttons in ResultsViewer

### Phase 9: Multi-User Toggle
- Conditional JWT middleware
- `auth.py` router (register, login, me)
- User-scoped DuckDB files
- `Login` React component (shown/hidden based on config)
- Auth context in frontend

### Phase 10: Polish
- Error handling middleware
- Loading states and optimistic updates in frontend
- Test suite (pytest for backend, vitest for frontend)
- Documentation
- Catppuccin 4‑variant theme system (Mocha/Macchiato/Frappé/Latte) with CSS custom properties
- JetBrains Mono font (Google Fonts)
- ThemeSwitcher component in sidebar (persisted to localStorage)
- All hardcoded Tailwind colors replaced with `bg-[var(--...)]` / `text-[var(--...)]`
- ISO 20022 search (`GET /iso20022/search?q=...`) with 300ms frontend debounce
- Financial batch-to-dataset (`POST /financial/batch-to-dataset`), creates reusable DuckDB datasets
- ISO→Template "Save as Template" button — flattens nested XSD fields, builds XML, saves via `POST /templates`, auto-navigates to Generation
- Fixed `mapXsdType` regex: `ActiveCurrencyCode` → `string` (was `float`), `CountryCode` → `string` (was `integer`)
- Optimized `search_messages()` to use default fallback data first (instant), then check cache
- Vite chunk splitting via `manualChunks` for `recharts` and `@tanstack/react-query` (eliminated 500KB chunk warning)
- Fixed Tailwind v4 `@import` ordering (JetBrains Mono import before `@import "tailwindcss"`)

---

## Key Libraries

### Backend
| Library | Purpose |
|---|---|
| `fastapi` | Web framework |
| `uvicorn` | ASGI server |
| `duckdb` | Embedded database |
| `faker` | Data generation |
| `yfinance` | Financial data |
| `lxml` | XSD parsing |
| `httpx` | HTTP client (ISO 20022 catalog) |
| `pandas` | XLSX export |
| `openpyxl` | Excel writer |
| `pyarrow` | Parquet export |
| `pyjwt` | JWT auth |
| `bcrypt` | Password hashing |
| `python-multipart` | File uploads |

### Frontend
| Library | Purpose |
|---|---|
| `react` + `react-dom` | UI framework |
| `typescript` | Type safety |
| `vite` | Build tool |
| `tailwindcss` | CSS framework |
| `@tanstack/react-query` | Server state |
| `recharts` | Charting (Financial panel) |

---

## Configuration

All configuration via environment variables (`.env`):

```env
# App
AUTH_ENABLED=false
SECRET_KEY=change-me

# Database
DUCKDB_PATH=./duckdb

# JWT (only when AUTH_ENABLED=true)
JWT_SECRET=change-me
JWT_EXPIRY_HOURS=24

# yfinance
YFINANCE_CACHE_TTL_QUOTES=30
YFINANCE_CACHE_TTL_HISTORICAL=3600

# ISO 20022
ISO20022_CACHE_TTL=3600

# Generation
MAX_ROWS_PER_DATASET=100000
MAX_DATASETS_PER_RUN=4
```

---

## Risk & Mitigation

| Risk | Mitigation |
|---|---|
| DuckDB write contention (multi-user) | Each user gets their own `.duckdb` file |
| Large datasets (100K+) slow UI | Paginated queries (`LIMIT/OFFSET`), virtual scrolling in React Table |
| yfinance rate limits | LRU cache with configurable TTL (30s quotes, 1h historical) |
| ISO 20022 site changes | Catalog scraper with error fallback; cached XSDs as backup |
| XSD complexity (imports, choices) | Parse only direct elements initially; support recursive types in v2 |
| Slow generation for 100K rows | Batch INSERT (10K rows at a time); streaming generator |
