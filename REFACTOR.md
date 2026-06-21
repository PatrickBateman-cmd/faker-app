# Refactoring Plan — Stability & Performance

Comprehensive code audit conducted June 2026. 72 issues found across Critical / High / Medium / Low severities.

## Second audit + fixes applied (June 2026)

A senior-code-reviewer pass found 40 additional issues (10 previously missed by the first audit). The following were fixed immediately:

| # | Fix | Files |
|---|---|---|
| R1 | **Template path traversal** — `_template_path()` validates name regex + confines to `TEMPLATES_DIR` | `template_library.py` |
| R2 | **Export COPY path** — temp files use `secrets.token_hex(16)`; service now returns `(filepath, download_name)` tuple | `export_service.py`, `routers/exports.py`, `tests/test_export.py` |
| R3 | **Kaggle `LIMIT` injection** — replaced `LIMIT {n}` with parameterized `LIMIT ?` | `kaggle_service.py` |
| R4 | **Migration atomicity** — each migration wrapped in `BEGIN`/`COMMIT`/`ROLLBACK` on the raw connection | `migrations.py` |
| R5 | **Aggregation sequence collision** — added `006_aggregation_sequence` migration (`seq_aggregation_id`); all aggregation INSERTs use `nextval('seq_aggregation_id')` | `migrations.py`, `transform_service.py` |
| R6 | **CORS origins** — `.strip()` each entry; explicit `allow_methods`/`allow_headers` (no wildcards with credentials) | `main.py` |
| R7 | **Template sync transaction** — `BEGIN`/`COMMIT` replaced by `db.transaction()`; `Lock` → `RLock` for re-entrance | `database.py`, `template_library.py` |
| R8 | **Cascading delete** — `delete_dataset` now also deletes from `metadata_aggregations` | `dataset_service.py` |
| R9 | **httpx client lifecycle** — `close_client()` added to `iso20022_service`; called in FastAPI lifespan | `iso20022_service.py`, `main.py` |
| R10 | **`keep_none` dedup** — broken correlated subquery replaced with `HAVING COUNT(*) = 1` | `transform_service.py` |
| R11 | **SSRF in XSD fetch** — host allowlist `{www.iso20022.org, iso20022.org}` added to `_fetch_xsd()` | `iso20022_service.py` |

Remaining high-priority items from the second audit (not yet fixed): sequential yfinance batch calls (#11), `enrich_dataset` full-table load (#10), formula + null interaction (#12), global `random.seed()` race (#26).

---

---

## Phase 1 — Critical: Security & Stability (~2–3h)

| # | Issue | Where | Fix |
|---|---|---|---|
| 1.1 | **SQL injection** — 13+ f-string SQL interpolations | `dataset_service.py`, `transform_service.py`, `export_service.py`, `generation_engine.py` | Validate table/column names against `^[a-zA-Z_][a-zA-Z0-9_]*$` OR whitelist via `information_schema.columns` with parameterized `?` |
| 1.2 | **DuckDB singleton not thread-safe** | `database.py:10-86` | Add `threading.Lock` around `execute()` or use per-request connections |
| 1.3 | **Row-by-row INSERT** — 100K `db.execute()` calls per dataset | `generation_engine.py:204-208` | Replace with `db.executemany()` — 20 round-trips instead of 100K |
| 1.4 | **XXE vulnerability** in XML parsing | `template_library.py:64` | Switch to `defusedxml.ElementTree.fromstring()` |
| 1.5 | **Path traversal via dataset name** | `export_service.py:22-27`, `router:13` | Sanitize filename: `re.sub(r'[^\w.-]', '_', name)`, use `os.path.basename()` |
| 1.6 | **Exported temp files never cleaned up** | `export_service.py:10-54` | Use `BackgroundTasks` to delete after response, or stream via `StreamingResponse` |
| 1.7 | **Open table access** via `/datasets/table/{name}/rows` | `datasets.py:33-39` | Remove endpoint or restrict to tables in `metadata_datasets` |
| 1.8 | **Bare `except` hiding errors** | `financial_service.py:38`, `generation_engine.py:158` | Log exceptions, catch specific error types |

### Detailed fixes

**1.1 SQL injection — column name validation**
Add this helper and use it wherever column/table names are interpolated:
```python
import re

_VALID_COLUMN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
_VALID_TABLE = re.compile(r'^dataset_[a-f0-9]+$')

def validate_column_name(name: str) -> str:
    if not _VALID_COLUMN.match(name):
        raise ValueError(f"Invalid column name: {name}")
    return name

def validate_table_name(name: str) -> str:
    if not _VALID_TABLE.match(name):
        raise ValueError(f"Invalid table name: {name}")
    return name
```

**1.2 Thread-safe DuckDB**
```python
import threading

class DuckDBManager:
    _lock = threading.Lock()

    def execute(self, sql, params=None):
        with self._lock:
            if params:
                return self._conn.execute(sql, params)
            return self._conn.execute(sql)
```

**1.3 `executemany` instead of loop**
```python
# Before: for row in batch_data: db.execute(insert, row)
# After:
db.execute(
    f'INSERT INTO "{table_name}" ({columns}) VALUES ({placeholders})',
    [item for row in batch_data for item in row],  # flatten
)
# Or use executemany:
self._conn.executemany(
    f'INSERT INTO "{table_name}" ({columns}) VALUES ({placeholders})',
    batch_data,
)
```

**1.6 Streaming export (no temp files)**
```python
from fastapi.responses import StreamingResponse

def export_csv_stream(dataset_id: str):
    meta = get_dataset(dataset_id)
    db = DuckDBManager.get_instance()
    # Use COPY TO '/dev/stdout' or read in chunks
    result = db.execute(f'COPY "{meta["table_name"]}" TO \'/dev/stdout\' (HEADER, DELIMITER \',\')')
    # Alternative: read via fetchdf and stream
    ...
    return StreamingResponse(iter(result), media_type="text/csv")
```

---

## Phase 2 — Performance (~1–2h)

| # | Issue | Where | Fix |
|---|---|---|---|
| 2.1 | **Row-by-row INSERT** (same as 1.3) | Phase 1 covers this | `executemany()` |
| 2.2 | **New `httpx.Client()` per request** — no connection reuse | `iso20022_service.py:88-91` | Module-level singleton `httpx.Client()` with pooling |
| 2.3 | **Template files re-read from disk on every API call** | `template_library.py:93-107` | In-memory cache with file-mtime invalidation |
| 2.4 | **Frontend refetches datasets every 5s** | `ResultsViewer.tsx:16` | Increase to 30s, add `refetchIntervalInBackground: false` |
| 2.5 | **`get_all_messages()` loads everything into memory** | `iso20022_service.py:191-203` | Add max page cap (50) |
| 2.6 | **`lru_cache` cleared on every XSD parse** | `iso20022_service.py:444` | Remove `_cache_clear()` call |

### httpx client singleton
```python
_HTTP_CLIENT: httpx.Client | None = None

def _get_client() -> httpx.Client:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        _HTTP_CLIENT = httpx.Client(timeout=10, follow_redirects=True,
                                    headers={"User-Agent": "FakerApp/0.1"})
    return _HTTP_CLIENT
```

---

## Phase 3 — Architecture & Code Quality (~2–3h)

| # | Issue | Where | Fix |
|---|---|---|---|
| 3.1 | **Metadata sync deletes all templates non-atomically** | `template_library.py:110-120` | Wrap in DuckDB transaction, use `INSERT OR REPLACE` |
| 3.2 | **Auth settings declared but not implemented** | `config.py:5-13` | Implement JWT middleware or remove settings |
| 3.3 | **Dead code `_SHARED_KEY_CACHE`** | `generation_engine.py:20` | Remove |
| 3.4 | **`strict=False` in `zip(columns, row)`** | `dataset_service.py:79` | Change to `strict=True` |
| 3.5 | **Inconsistent error handling across routers** | All routers | Standardize global exception handler |
| 3.6 | **Nested fields limited to 10, XSD elements to 50** | `iso20022_service.py:285,378` | Remove hard caps or log warning on truncation |
| 3.7 | **`generate_from_xsd` hard-codes 10 rows** | `iso20022_service.py:478` | Accept `count` parameter |
| 3.8 | **`import random` inside hot loop** | `iso20022_service.py:488-544` | Move to module top |

### Global exception handler
```python
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
```

---

## Phase 4 — Polish & UX (~1h)

| # | Issue | Where | Fix |
|---|---|---|---|
| 4.1 | **UUID truncated to 8 chars** | `generation_engine.py:136`, `transform_service.py:62` | Use full UUID or DB sequence |
| 4.2 | **`strict=False` in more places** | `dataset_service.py:79,104` | `strict=True` |
| 4.3 | **Export dropdown closes before user can click** | `ResultsViewer.tsx:140-163` | Click-based toggle instead of hover |
| 4.4 | **Duplicated type definitions** | `types/template.ts` vs `types/generation.ts` | Consolidate into shared types |
| 4.5 | **Apply button logs to console** | `TemplateLibrary.tsx:141` | Wire to generation page |
| 4.6 | **Unused `useEffect` import** | `AggregationPanel.tsx:1` | Remove |
| 4.7 | **`onResult` uses `unknown`** | `AggregationPanel.tsx:23` | Define typed response interface |
| 4.8 | **Delete mutation lacks error UI** | `ResultsViewer.tsx:27-36` | Add `onError` handler |
| 4.9 | **Financial panel fetches on mount** | `FinancialPanel.tsx:52-73` | Gate behind explicit Search click |
| 4.10 | **Health check fails if DuckDB is down** | `health.py:8-12` | Return degraded status instead |

---

## Effort Summary

| Phase | Scope | Time |
|---|---|---|
| **Phase 1** — Security & Stability | 8 backend files, 8 issues | **2–3 hours** |
| **Phase 2** — Performance | 5 backend + 1 frontend, 6 issues | **1–2 hours** |
| **Phase 3** — Architecture | 6 backend files, 8 issues | **2–3 hours** |
| **Phase 4** — Polish & UX | 5 frontend + 2 backend, 10 issues | **1 hour** |
| **Total** | ~13 files, 32 high-priority issues | **~6–9 hours** |

---

## Additional Fixes (June 2026 — post-refactoring)

| # | Fix | Where | Detail |
|---|---|---|---|
| 5.1 | **ISO search was slow (60s because it scraped live site per domain)** | `iso20022_service.py:search_messages()` | Switched to default fallback data first (instant), cache-only for extras |
| 5.2 | **`mapXsdType` regex falsely mapped `currency` → `float`** | `Iso20022Panel.tsx:mapXsdType()` | Removed `currency` from float regex — `ActiveCurrencyCode` now correctly maps to `string` |
| 5.3 | **`mapXsdType` regex falsely mapped `count`/`id` → `integer`** | `Iso20022Panel.tsx:mapXsdType()` | Tightened integer regex to `(numeric\|integer\|year\|index)` — `CountryCode` now correctly maps to `string` |
| 5.4 | **ISO template files on disk had wrong types** | `backend/app/templates/*.xml` | Fixed `Currency type="float"` → `type="string"`, `Country type="integer"` → `type="string"` in both ISO templates |
| 5.5 | **Vite chunk >500KB warning** | `vite.config.ts` | Added `build.rollupOptions.output.manualChunks` for `recharts` and `@tanstack/react-query` |
| 5.6 | **CSS `@import` ordering error** | `index.css` | Moved Google Fonts `@import` before `@import "tailwindcss"` (Tailwind v4 requirement) |
