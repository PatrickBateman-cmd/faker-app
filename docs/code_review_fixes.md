# Code Review Fixes

Two-phase remediation of issues found during senior engineer code review of the Faker App backend. All 40 backend tests pass after changes.

## Phase 0 — Critical Bug Fixes (6 items)

### 0.1 Thread safety — `database.py`
- **Problem:** `get_connection()` exposed the raw DuckDB connection without a lock. Multiple threads could execute concurrent writes, corrupting the single-writer DuckDB database.
- **Fix:** Removed `get_connection()`. Added a locked `executemany(sql, params)` method on `DuckDBManager` using the same `threading.Lock` as `execute()`.
- **Call sites updated:** 7 locations across `generation_engine.py` (4) and `financial_service.py` (3) now use `db.executemany()`.

### 0.2 Config path — `config.py`
- **Problem:** `.env` was loaded via `env_file=".env"`, which resolves relative to CWD rather than the project root. Running from `backend/` misses the `.env` file at the repo root.
- **Fix:** Changed to `env_file=Path(__file__).parent.parent.parent / ".env"`, resolving from the config file location.

### 0.3 Cache crash — `iso20022_service.py`
- **Problem:** `get_messages.cache_info().hits > 0` assumed `get_messages` was decorated with `@cache`/`@lru_cache`, but it was not. This raised `AttributeError` at runtime.
- **Fix:** Wrapped in `try/except AttributeError` to gracefully handle missing cache.
- **(Later removed in Phase 1.2 as dead code.)**

### 0.4 Path traversal — `template_library.py`
- **Problem:** `get_template_by_filename()` used `TEMPLATES_DIR / filename` without validation. A filename like `../../etc/passwd` could traverse outside the templates directory.
- **Fix:** Added `(TEMPLATES_DIR / filename).resolve().startswith(str(TEMPLATES_DIR.resolve()))` guard.

### 0.5 XXE in XSD parser — `iso20022_service.py`
- **Problem:** `etree.fromstring(xsd_content)` parsed XML with external entity resolution enabled, making the parser vulnerable to XML External Entity (XXE) injection.
- **Fix:** Added a module-level `_SECURE_XSD_PARSER = etree.XMLParser(resolve_entities=False, no_network=True)` and passed it to `fromstring()`. Kept `lxml` (rather than `defusedxml`) because the parser relies on `.xpath()`, `.nsmap`, and `XMLSyntaxError`.

### 0.6 Date type mapping — `cli/iso20022.py`
- **Problem:** The `"time"` check came after `"date"` in `_xsd_to_field_type()`, so `dateTime` XSD types matched `"date"` first and were incorrectly mapped as `"date"` instead of `"datetime"`.
- **Fix:** Moved the `"time"` check before the `"date"` check.

## Phase 1 — Code Quality & Tech Debt (8 items)

### 1.1 Unused import — `iso20022_service.py`
- **Removed** `from functools import lru_cache` — no function in the module uses the decorator.

### 1.2 Dead code — `iso20022_service.py`
- **Removed** the `cache_info()` block (10 lines) — `get_messages` is not decorated with `@cache`, so the branch was permanently dead code.

### 1.3 Silent formula errors — `generation_engine.py`
- **Problem:** Two `except Exception: row.append(field.formula or "")` blocks silently swallowed Jinja template rendering failures.
- **Fix:** Added `logger.exception(...)` before the fallback so failures are visible in logs.

### 1.4 UUID truncation — 6 files
- **Problem:** CLI and TUI displayed `dataset_id[:8] + "..."` instead of the full 36-char UUID, despite the API already returning full UUIDs.
- **Files fixed:** `cli/generate.py`, `cli/datasets.py`, `cli/financial.py`, `cli/transform.py` (2 locations), `tui/screens/datasets.py`.
- **Fix:** Replaced `[:8] + "..."` with the full `dataset_id`.

### 1.5 Silent fallbacks — 5 locations
- `cli/iso20022.py` — Unknown XSD types now logged as warning instead of silent `"string"`.
- `iso20022_service.py` — Unknown field types now logged as warning instead of silent `"text"`.
- `generation_engine.py` — Unknown generators now logged as warning instead of silent `fake.word()`.
- `generation_engine.py` — Unknown field types logged as debug instead of silent `VARCHAR`.
- `routers/exports.py` — Temp file cleanup failure now logged.

### 1.6 Type safety — `generation_engine.py`
- **Problem:** `_check_condition()` compared `field_val >= val` where types could mismatch (e.g., `str >= int`), raising `TypeError` at runtime.
- **Fix:** Wrapped comparison operators in `try/except TypeError`, returning `False` (skip field) with a warning log.

### 1.7 Test quality — `tests/conftest.py`
- Removed redundant `except Exception: pass` wrappers around pre-test `close_instance()` calls.
- Removed defensive `hasattr(tl, '_cache')` guard — `_cache` is always set.

### 1.8 Minor cleanups
- **Removed** unused `timedelta` imports from `generation_engine.py` and `iso20022_service.py`.
- **Removed** defensive `hasattr(resp, "model_dump")` from `cli/generate.py` — `generate_datasets` always returns a Pydantic model.
- `cli/main.py` — DB query errors now shown to user via `console.print` instead of silent `dataset_count=0`.
- `routers/health.py` — Health check exceptions now logged.
- `tui/screens/dashboard.py` — Stats load failures now logged instead of silent `pass`.
