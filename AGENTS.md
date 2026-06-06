# Repository Guidelines

## Commands

- `cp .env.example .env` — prerequisite before first start.
- `./start.sh` — backend (uvicorn) + frontend (Vite); auto-creates `.venv`, installs deps.
- `./start.sh --with-async` — also starts Celery worker + beat (needs Redis).
- `./start.sh --skip-frontend` — backend only.
- `./stop.sh` / `./restart.sh` — stop/restart local services.
- `docker compose up` — full stack (Postgres, Redis, backend, frontend, celery).
- `./start-docker.sh` / `./stop-docker.sh` — Docker Compose wrappers.
- `pytest` — all backend tests (run from repo root; `pytest.ini` sets `pythonpath = backend`). No Docker required.
- `pytest backend/tests/test_orders.py::test_name -q` — single test.
- `cd frontend && npm run dev` — Vite dev server.
- `cd frontend && npm run build` — type-check (`vue-tsc --noEmit`) then build.
- `bash ./async-health.sh` — check Celery worker/beat health.

## Architecture

- **Backend entrypoint**: `backend/app/main.py` — FastAPI with lifespan that calls `initialize_database()` (creates tables, runs hand-rolled schema upgrade, seeds default account).
- **API mount**: `backend/app/api/router.py` mounts all routes under `settings.api_prefix` (default `/api/v1`).
- **Config**: `backend/app/core/config.py` — `pydantic-settings` reading from repo-root `.env`.
- **No Alembic** — schema migrations are inline in `backend/app/db/init_db.py` (checks required columns).
- **Strategy plugins**: classes in `backend/app/strategy/strategies/` implementing a base, registered by type mapping.
- **Market data**: provider fallback chain `SinaQuoteProvider → EastMoneyQuoteProvider → AkshareQuoteProvider` in `backend/app/market/service.py`.
- **Frontend entrypoint**: `frontend/src/main.ts` — Vite + Vue 3 + Pinia + Vue Router + Element Plus + Tailwind CSS.
- **No CI/CD** — no `.github/workflows/`; all verification is local.
- SuperUser gate: monitoring routes use `get_current_superuser`; frontend `/monitoring` guarded by router redirect.

## Testing

- **No Docker needed**: `conftest.py` overrides `DATABASE_URL` to a temp SQLite, patches `_is_trading_time` to always true, and provides a pre-authenticated `TestClient`.
- Test files in `backend/tests/test_*.py`, functions `test_*`.
- No frontend test framework configured.

## Conventions

- Business logic in `backend/app/*/service.py`; route handlers are thin wrappers.
- Preserve Chinese UI copy unless asked to change.
- Commit style: Conventional Commits with scope, e.g. `feat(market):`, `style(StrategiesView):`.
- `.env` at repo root for all configuration; `VITE_API_BASE_URL` controls frontend API targeting.
- `artifacts/` — RL training outputs (gitignored). `reference/` — external ref material (gitignored).
- `.local/` — runtime data/logs/pid files (gitignored).
