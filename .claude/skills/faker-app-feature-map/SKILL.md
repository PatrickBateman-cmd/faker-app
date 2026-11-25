---
name: faker-app-feature-map
description: Map of how a faker-app feature threads through every layer (schema, service, router, CLI, frontend types/api/component, tests, docs), with the balance feature as the worked example. Use when adding or changing a feature end-to-end, or tracing where a behaviour lives.
---

# faker-app feature map

CLAUDE.md covers conventions. **ARCHITECTURE.md** has the design diagrams: system architecture, the data-flow pipelines (generation, Kaggle import, export, aggregation/dedup), the DB schema and the migration history. This skill is the missing piece: **every file a feature touches, in order**, so nothing gets left unwired.

Worked example: the balance-derivation feature, `POST /datasets/{id}/balances`, which derives account balances from an existing transactions dataset into a new snapshot. Don't confuse it with the generation-time balance sets in `generation_engine/balance.py` (tested in `test_balance.py`), which hook into `POST /generate` instead.

## Backend: `backend/app/`

| # | File | What goes there | Balance example |
|---|---|---|---|
| 1 | `schemas/<domain>.py` | Pydantic request/response models | `schemas/balance.py` (`BalanceDeriveRequest`, `BalanceDeriveResponse`) |
| 2 | `services/<domain>_service.py` | All logic and all `DuckDBManager` access. Validate identifiers, use `?` params, `db.transaction()` for multi-statement work, `executemany` for batches | `services/balance_service.py` |
| 3 | Producing a new dataset? | Use the shared helpers in `services/dataset_service.py`: `get_dataset_table_name(id)` to resolve and validate the source, then build the table and call `register_transformed_dataset(...)` **inside the same `db.transaction()`** | `derive_balances()` builds, perturbs, then registers |
| 4 | `routers/<domain>.py` | Thin layer: call the service and map errors. `LookupError` → 404, `ValueError` → 400, anything else → 500 | `routers/balance.py` |
| 5 | `main.py` | Add to the `from app.routers import (...)` tuple **and** `app.include_router(<domain>.router, prefix="")` | both lines added for `balance` |
| 6 | Schema change? | New `Migration` entry in `core/migrations.py`. If a new metadata table references `dataset_id`, add it to the cascade in `dataset_service.delete_dataset` | not needed; it reuses `metadata_recon_breaks` |

## CLI: `backend/cli/`

| 7 | `cli/<domain>.py` | Typer `app` that calls services in-process (no HTTP) | `cli/balance.py` |
|---|---|---|---|
| 8 | `cli/main.py` | `app.add_typer(_<domain>.app, name="<domain>", help=...)` | `faker balance ...` |

TUI (`backend/tui/screens/`) is optional; balance has no TUI screen.

## Frontend: `frontend/src/`

| 9 | `types/<domain>.ts` | Interfaces mirroring the Pydantic models field for field | `types/balance.ts` |
|---|---|---|---|
| 10 | `api/<domain>.ts` | `fetch("/api/...")` (Vite strips `/api` and proxies to :8000). Throw on `!res.ok` | `api/balance.ts` → `deriveBalances()` |
| 11 | `components/<Name>/<Name>.tsx` | The UI | `components/BalancePanel/BalancePanel.tsx` |
| 12 | Mount it | **A whole page:** a `<Route>` in `App.tsx` plus a nav item in `components/Layout/Sidebar.tsx`. **A per-dataset panel:** in `ResultsViewer.tsx`, extend `SectionKey`, `SECTION_LABELS`, `ALL_SECTIONS` and `DEFAULT_COLLAPSED`, and add the `{key === "..." && ...}` render block | balance is a per-dataset panel |

## Tests: `backend/tests/`

Fixtures live in `conftest.py`: `db` gives a temp DuckDB, and `client` is a FastAPI `TestClient` on a temp DB with the lifespan running.

| 13 | `test_<domain>.py` | Service logic, using the `db` fixture | `test_balance_derive.py` |
|---|---|---|---|
| 14 | `test_<domain>_api.py` | HTTP contract and error codes, using `client`. Generate a source dataset via `POST /generate` first | `test_balance_derive_api.py` |
| 15 | `test_cli_<domain>.py` | `typer.testing.CliRunner` against `cli.main.app` | `test_cli_balance.py` |

Run them with the commands in the `run-faker-app` skill.

## Docs

| 16 | `CLAUDE.md` | API endpoints table, plus any new convention or gotcha |
|---|---|---|
| 17 | `ARCHITECTURE.md` | New data-flow diagram, metadata table or sequence |
