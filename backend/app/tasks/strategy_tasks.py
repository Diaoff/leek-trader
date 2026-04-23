from app.core.celery_app import celery_app
from app.core.db import SessionLocal
from app.strategy.service import StrategyService


@celery_app.task(name="app.tasks.strategy_tasks.run_strategy_cycle_task")
def run_strategy_cycle_task(strategy_ids: list[int] | None = None) -> dict[str, object]:
    service = StrategyService()
    with SessionLocal() as db:
        runs = service.run_active_strategies(db, strategy_ids=strategy_ids)

    return {
        "status": "completed",
        "task": "run_strategy_cycle",
        "count": len(runs),
        "strategy_ids": [run.strategy_id for run in runs],
        "results": [
            {
                "id": run.id,
                "strategy_id": run.strategy_id,
                "status": run.status,
                "signal": run.signal,
            }
            for run in runs
        ],
    }
