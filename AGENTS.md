# Repository Guidelines

## Project Structure & Module Organization

This repository contains a full-stack trading simulator. Backend code lives in `backend/app`, with FastAPI routes in `api`, SQLAlchemy models in `models`, Pydantic schemas in `schemas`, and feature services such as `market`, `portfolio`, `strategy`, and `trading`. Backend tests are in `backend/tests`. Frontend code lives in `frontend/src`, with Vue views in `views`, Pinia stores in `stores`, API clients in `api`, shared types in `types`, and utilities in `utils`. Root scripts start services; `reference/` is external reference material and should usually remain unchanged.

## Build, Test, and Development Commands

- `./start.sh`: start local backend and frontend using the Python virtualenv and Node modules.
- `./stop.sh` / `./restart.sh`: stop or restart local services.
- `docker compose up`: run Postgres, Redis, backend, and frontend.
- `pytest`: run all backend tests from the repository root.
- `pytest backend/tests/test_orders.py -q`: run one backend test module.
- `cd frontend && npm run dev`: start the Vite development server.
- `cd frontend && npm run build`: type-check Vue and build assets.

## Coding Style & Naming Conventions

Use Python type hints and keep business logic in services rather than route handlers. Name backend test files `test_*.py` and functions `test_*`. Vue views use PascalCase names such as `PortfolioView.vue`; TypeScript API modules, stores, and utilities use camelCase or feature names. Preserve existing Chinese UI copy unless asked to change it. No dedicated formatter or lint script is configured, so match nearby style.

## Testing Guidelines

Backend tests use `pytest`; `pytest.ini` sets `pythonpath = backend`. Tests use isolated SQLite fixtures in `backend/tests/conftest.py`, so Docker is not required for normal backend test runs. Add regression tests for bug fixes and service-level tests for business rules. Run the narrowest relevant test first, then `pytest` for broader confidence. For frontend changes, run `cd frontend && npm run build`.

## Commit & Pull Request Guidelines

Recent commits use Conventional Commit-style prefixes, often with scopes, for example `feat(market): ...` or `style(StrategiesView): ...`. Use imperative subjects and specific scopes when useful. Pull requests should include a concise summary, linked issue or context, screenshots for UI changes, and the exact tests/builds run. Note verification gaps or required environment variables.

## Security & Configuration Tips

Configuration is read from the repository-level `.env`. `DATABASE_URL` defaults to local Postgres, and `VITE_API_BASE_URL` controls frontend API targeting. Do not commit secrets, local logs, generated databases, or virtualenv/node dependency directories.
