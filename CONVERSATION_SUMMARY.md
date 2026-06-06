# Conversation Summary — June 2026

## Overview
Built a full-stack synthetic data generator (FastAPI + DuckDB + React 19) with ISO 20022 integration, yfinance financial data, CLI, tests, and Docker Compose deployment.

## What was done

### 1. Refactoring Audit (24/25 items)
- SQL injection: table/column name validation on all f-string SQL spots
- Thread safety: `threading.Lock` on DuckDBManager
- Batch INSERT: `executemany` replaces row-by-row loop
- XXE: `defusedxml.ElementTree` replaces stdlib XML
- Path traversal: `os.path.basename` sanitization
- Temp file leak: `BackgroundTasks` cleanup after export
- Removed open `/datasets/table/{name}/rows` endpoint
- Bare excepts → specific types with logging
- httpx pool: single reused `httpx.Client`
- Removed stale `_cache_clear()` and `_SHARED_KEY_CACHE`
- `import random` moved to module top
- Template sync wrapped in `BEGIN/COMMIT`
- Global exception handler returning 500
- Frontend refetch 5s→30s, background refetch disabled
- Full 36-char UUIDs for dataset IDs
- Template file-mtime caching

### 2. Features (7 phases)
- **Formula evaluation**: Jinja2 cross-field templates (`{{first_name|lower}}@example.com`)
- **Null probability**: per-field NULL injection
- **Weighted random elements**: distribution weights for enum fields
- **Conditional generation**: `condition: "age >= 18"` skips fields
- **Financial enrich**: yfinance join on existing datasets
- **Offline ISO cache**: DuckDB cache with 1h TTL
- **Dataset charting**: Recharts bar/line/pie
- **Dataset rename**: API + CLI
- **JSON Lines export**: alongside CSV/Parquet/XLSX
- **Database migrations**: auto-run on startup
- **Toast notifications**: replaces `alert()`
- **Dashboard redesign**: stats cards + recent datasets + quick actions
- **Field drag & drop**: reorder in Data Definition Pane
- **Financial interval selector**: period + interval dropdowns
- **React-router**: URL-based navigation with `/datasets/:id`
- **Docker Compose**: production deployment with nginx
- **Tests**: 40 backend pytest tests + 2 frontend vitest tests

### 3. Documentation
- `AGENTS.md` — full run, architecture, conventions, features, known issues
- `README.md` — project overview, setup, all features documented
- `CHEATSHEET.md` — complete CLI + curl reference

### Final commit
`2e016ad` — 55 files, +3988/-390 lines
