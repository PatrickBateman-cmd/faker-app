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

### Final commits (Phase 1)
`2e016ad` — 55 files, +3988/-390 lines

---

### 4. TUI — Textual Terminal UI (Phase 2)

#### What was fixed
- **Import fix**: `.venv/bin/faker` inserts `backend/` into `sys.path` via `os.path.abspath(os.path.join(__file__, "..", "..", ".."))` (hatchling `.pth` files unreliable).
- **Screen navigation**: `switch_screen` replaces `push_screen` to avoid stacking duplicate screens; `DashboardScreen` removed from `App.compose()` to prevent keyboard event stealing.
- **Widget kwargs**: `FieldRow` and `FieldList` now accept `**kwargs` → `super().__init__(**kwargs)`, fixing `unexpected keyword argument 'id'` errors.
- **Catppuccin Mocha CSS**: `app.tcss` with `#1e1e2e` background, `#cdd6f4` text, `#89b4fa` accent, `#f38ba8` red, `#a6e3a1` green; scrollable screens, compact field rows, consistent button variants.

#### Screens (all 6)
| Screen   | Description |
|----------|-------------|
| Dashboard | 3 stat cards via DuckDB metadata |
| Generation | Flat/grouped toggle, vim-mode field editor, calls `generate_datasets()` |
| Datasets | Sidebar list, paginated table, export/delete |
| Financial | Quote card + Braille-dot chart (`_braille_line()`), batch fetch |
| Templates | Search + list from `template_library` |
| ISO 20022 | Search + results from `iso20022_service` |

#### Git history
- `tui` branch pushed → merged fast-forward into `main` → pushed to origin.
- Final commit `31866a2` — 18 files, +1270/-1 lines.

### Known issues (carried forward)
- Auth settings declared but not implemented.
- Export dropdown click toggle closes on blur with 200ms delay.
- Financial panel does not cache historical data across page navigations.
- Some XSD `<xs:include>` / `<xs:import>` directives are ignored.
- No frontend test coverage for components beyond ThemeSwitcher.
