# Contributing

Leek Trader is currently scoped as a local, single-user A-share research and paper-trading simulator. Contributions should preserve that boundary: no real broker connectivity, no production multi-tenant isolation, no billing, and no quota systems unless the project scope is explicitly changed.

## Local Development

1. Create `.env` from `.env.example` and adjust local database/Redis settings.
2. Start the app with `./start.sh` or `./start.sh --with-async` when Celery tasks are needed.
3. Run backend tests from the repository root with `pytest`.
4. Run frontend verification with `cd frontend && npm run build` after UI/API type changes.

## Change Guidelines

- Keep diffs small and reversible.
- Reuse existing FastAPI services, SQLAlchemy models, Vue views, Pinia stores, and API clients before adding new layers.
- Add regression tests for backend behavior changes.
- Use the standard library for simple export/reporting features; do not add dependencies without a clear need.
- Preserve existing Chinese UI copy unless a task explicitly asks to change it.

## Verification Checklist

Before opening a PR, include the exact commands you ran and any known gaps:

- `pytest backend/tests/test_strategies.py -q` for strategy/template/version changes.
- `pytest backend/tests/test_reporting.py -q` for reporting/export changes.
- `pytest backend/tests/test_backtest.py -q` for backtest/review changes.
- `pytest backend/tests/test_rl_training.py -q` for RL workflow changes.
- `cd frontend && npm run build` for frontend changes.

## Commit Notes

Prefer imperative, scoped subjects such as `feat(strategies): add local version comparison`. When useful, add trailers such as `Tested:` and `Not-tested:` to make verification history explicit.
