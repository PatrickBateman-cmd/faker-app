---
name: run-faker-app
description: Launch and drive the faker-app locally (FastAPI backend on :8000 + Vite frontend on :5173) and run its backend/frontend tests and typecheck from Claude Code on this Mac, working around the sandbox, uv and nvm pitfalls.
---

# Run faker-app

Verified 2026-11-25 on macOS (Darwin 25), Claude Code with the Bash sandbox on.

## Pitfalls (why the CLAUDE.md commands fail here)

- **Don't use `uv run`.** It picked Python 3.15 and started deleting `backend/.venv` to rebuild it. The sandbox stopped it halfway (it can't touch `certifi/cacert.pem` because `*.pem` is denied), which left the venv without `bin/`. Run `backend/.venv/bin/*` directly.
- **Don't use `npm` or `node`.** In Claude's shell they are nvm lazy-load functions that loop forever (`_load_nvm` not found, then `maximum nested function level reached`). Call the nvm node binary by path.
- **Port binding is blocked in the sandbox** (`listen EPERM`). Both servers need `dangerouslyDisableSandbox: true`, unless `sandbox.network.allowLocalBinding: true` is set.

## 1. Make sure the venv is healthy

```bash
ls /Users/krzysztof.czaderna/faker-app/backend/.venv/bin/uvicorn
```

If it's missing, rebuild it with Python 3.14 (pinned, matching `requires-python`). Run this **outside the sandbox** because of the `.pem` deny:

```bash
cd /Users/krzysztof.czaderna/faker-app/backend && uv sync --python 3.14 --extra dev
```

## 2. Start both servers (background, sandbox disabled)

Backend:
```bash
cd /Users/krzysztof.czaderna/faker-app/backend && exec .venv/bin/uvicorn app.main:app --reload --port 8000
```

Frontend:
```bash
cd /Users/krzysztof.czaderna/faker-app/frontend && NODE_BIN=$(ls -d ~/.nvm/versions/node/*/bin | sort -V | tail -1) && PATH="$NODE_BIN:$PATH" exec "$NODE_BIN/node" node_modules/vite/bin/vite.js
```

Run each with `run_in_background: true` and `dangerouslyDisableSandbox: true`.

## 3. Wait for ready

Wait in a background Bash `until`/`for` loop, not a foreground sleep. Grep each server's output file for:
- backend: `Application startup complete` (failure: `Error|Traceback`)
- frontend: `ready in` (failure: `error|EPERM`)

The first backend start can take ~5s (yfinance import).

## 4. Drive it

- UI: http://localhost:5173. `open` is blocked in the sandbox, so give the user the URL.
- API smoke (not yet verified; a curl to localhost was denied by a permission prompt in the session that wrote this):
  ```bash
  curl -s http://localhost:8000/health
  curl -s http://localhost:5173/api/info   # through the Vite proxy
  ```

## Run the tests (works inside the sandbox)

Verified 2026-11-25: 159 backend tests pass, 2 frontend tests pass, typecheck clean.

```bash
cd /Users/krzysztof.czaderna/faker-app/backend && .venv/bin/pytest tests/ -q
```

```bash
cd /Users/krzysztof.czaderna/faker-app/frontend && NODE_BIN=$(ls -d ~/.nvm/versions/node/*/bin | sort -V | tail -1) && export PATH="$NODE_BIN:$PATH" \
  && "$NODE_BIN/node" node_modules/vitest/vitest.mjs run \
  && "$NODE_BIN/node" node_modules/typescript/bin/tsc -b --noEmit
```

Use `tsc -b` (build mode, as `npm run build` does), not plain `tsc --noEmit`.

## Stop / notes

- Stop the servers with TaskStop on their background task IDs.
- DuckDB is single-writer: stop the backend before running `faker tui` or direct CLI queries.
