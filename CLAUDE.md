# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Full stack with Docker Compose
- `docker compose up` — start Postgres, Redis, FastAPI backend, and Vite frontend
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173`

### Backend development
- `cd backend && pip install -r requirements.txt`
- `cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
- The backend reads settings from the repo-level `.env` via `app.core.config.Settings`.

### Frontend development
- `cd frontend && npm install`
- `cd frontend && npm run dev`
- `cd frontend && npm run build`
- The frontend calls `VITE_API_BASE_URL` if set, otherwise defaults to `http://localhost:8000/api/v1`.

### Tests
- `pytest` — run all backend tests from the repository root
- `pytest backend/tests/test_orders.py -q` — run one test file
- `pytest backend/tests/test_orders.py::test_create_order_persists_and_lists_order -q` — run one test

## Architecture

This repo is a small full-stack stock paper-trading MVP with a FastAPI backend and a Vue 3 frontend.

### Backend
- Entry point: `backend/app/main.py`
- API composition: `backend/app/api/router.py` mounts all routes under `/api/v1`
- Configuration: `backend/app/core/config.py` uses `pydantic-settings` and defaults to Docker service hostnames for Postgres/Redis
- Database setup: `backend/app/core/db.py` creates the SQLAlchemy engine/session; `backend/app/db/init_db.py` creates tables on startup and seeds a default simulated account

The backend is organized mostly by domain:
- `app/api/` exposes REST endpoints
- `app/models/` contains SQLAlchemy persistence models for accounts, orders, positions, trades, cash flows, and strategy metadata
- `app/schemas/` contains request/response models
- `app/*/service.py` files hold business logic instead of pushing logic into route handlers

Important flows:
- Market data: `backend/app/market/service.py` fetches quotes through a provider fallback chain (`SinaQuoteProvider` → `EastMoneyQuoteProvider` → `AkshareQuoteProvider`) and normalizes them into API schemas
- Strategies: `backend/app/strategy/service.py` maps strategy types to plugin classes in `backend/app/strategy/strategies/` and evaluates them against in-memory demo price series
- Trading: `backend/app/trading/service.py` is the core execution path for order placement, risk checks, matching, position/account updates, trade creation, and cash-flow recording
- Portfolio: `backend/app/portfolio/service.py` derives summary metrics from account and position state

There are also task modules under `backend/app/tasks/`, but the current API paths are primarily synchronous service calls.

### Frontend
- Entry point: `frontend/src/main.ts`
- Shell/layout: `frontend/src/App.vue`
- Routing: `frontend/src/router/index.ts`
- Global state: `frontend/src/stores/app.ts`
- API wrappers: `frontend/src/api/*.ts`
- Page-level UI: `frontend/src/views/*.vue`

The frontend is a Vite + Vue 3 + Pinia + Vue Router app using Element Plus components.

The main UI structure is feature-oriented:
- Dashboard shows portfolio summary plus MVP module status
- Market page reads `/quotes`
- Strategies page reads `/strategies`
- Portfolio page is the main trading screen: it submits orders, then refreshes orders, positions, and portfolio summary together

### Testing notes
- Tests live under `backend/tests/`
- `backend/tests/conftest.py` overrides `DATABASE_URL` to a temporary SQLite database per test run, reloads the config/db modules, recreates schema, and seeds the default account
- Because of that setup, backend tests do not require Docker services to be running

## Repository-specific notes
- There is currently no dedicated lint script or frontend test script configured in `frontend/package.json`
- `pytest.ini` sets `pythonpath = backend`, so backend imports resolve when tests are run from the repo root
- Much of the visible product copy is in Chinese; preserve that style unless the task explicitly asks to change it
