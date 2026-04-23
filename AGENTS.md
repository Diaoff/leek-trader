# Leek Trader Agent Guide

## Essential Commands

### Full Stack Development
- **Start all services**: `./start.sh` (uses local Python venv and Node modules)
- **Stop services**: `./stop.sh`
- **Restart services**: `./restart.sh`
- **Manual Docker compose**: `docker compose up` (Postgres, Redis, backend, frontend)

### Backend Development
- **Install deps**: `cd backend && pip install -r requirements.txt`
- **Run server**: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
- **Backend reads config** from repo-level `.env` via `app.core.config.Settings`

### Frontend Development
- **Install deps**: `cd frontend && npm install`
- **Dev server**: `cd frontend && npm run dev`
- **Production build**: `cd frontend && npm run build`
- **Frontend API base**: Uses `VITE_API_BASE_URL` if set, else defaults to `http://localhost:8000/api/v1`

### Testing
- **All backend tests**: `pytest` (from repo root)
- **Single test file**: `pytest backend/tests/test_orders.py -q`
- **Single test function**: `pytest backend/tests/test_orders.py::test_create_order_persists_and_lists_order -q`
- **Note**: Backend tests use temporary SQLite DB via conftest.py - no Docker services needed

## Architecture Notes

### Backend Organization
- **Entry point**: `backend/app/main.py`
- **API routing**: `backend/app/api/router.py` mounts all routes under `/api/v1`
- **Domain structure**: 
  - `app/api/` - REST endpoints
  - `app/models/` - SQLAlchemy models (accounts, orders, positions, etc.)
  - `app/schemas/` - Pydantic request/response models
  - `app/*/service.py` - Business logic (preferred over route handlers)

### Key Flows
- **Market data**: `backend/app/market/service.py` → provider fallback chain (Sina → EastMoney → Akshare)
- **Strategies**: `backend/app/strategy/service.py` → maps types to plugin classes in `backend/app/strategy/strategies/`
- **Trading**: `backend/app/trading/service.py` → core execution path (order placement, risk checks, matching, updates)
- **Portfolio**: `backend/app/portfolio/service.py` → derives summary metrics from account/position state

### Frontend Organization
- **Entry point**: `frontend/src/main.ts`
- **Layout**: `frontend/src/App.vue`
- **Routing**: `frontend/src/router/index.ts`
- **State management**: `frontend/src/stores/app.ts` (Pinia)
- **API wrappers**: `frontend/src/api/*.ts`
- **Pages**: `frontend/src/views/*.vue` (feature-oriented)

## Important Conventions

### Environment Variables
- **Database**: Defaults to `postgresql+psycopg://postgres:postgres@localhost:5432/leek_trader`
- **Override**: `DATABASE_URL='custom_url' ./start.sh`
- **Backend API**: `VITE_API_BASE_URL` affects both backend (exported) and frontend

### Code Style
- **Visible copy**: Much UI text is in Chinese - preserve this style unless explicitly asked to change
- **No lint/formatter**: Currently no dedicated lint script or frontend test script in configs
- **Test isolation**: `pytest.ini` sets `pythonpath = backend` for proper imports when testing from repo root

### Project State
- **Asynchronous features**: Market refresh, strategy runs, and order matching use Celery tasks with Beat scheduling
- **Worker/Beat docs**: See sections 128-150 in README.md for current async status and limitations
- **Verification**: Recent validation showed 81 backend tests passing and successful frontend build (see README lines 173-178)

## Common Gotchas

### Service Dependencies
- **Start order**: Backend must be running before frontend for proper API proxying
- **Port conflicts**: Scripts automatically detect and handle stale PID files
- **Log locations**: Backend logs → `.local/logs/backend.log`, Frontend logs → `.local/logs/frontend.log`

### Testing Specifics
- **Test DB**: Each test gets isolated SQLite database (conftest.py)
- **Mocking**: Tests often mock external services (risk checks, quote fetching)
- **Async testing**: Market/strategy/trading tasks have dedicated test files

### Development Workflow
- **Env file**: Repo-level `.env` overrides Docker-compose defaults
- **Virtualenv**: Scripts auto-create/use `.venv` for Python deps
- **Node modules**: Scripts auto-install/use `frontend/node_modules`