import logging

from app.core.celery_app import celery_app
from app.core.db import SessionLocal
from app.strategy.service import StrategyService

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.strategy_tasks.run_strategy_cycle_task", bind=True)
def run_strategy_cycle_task(self, strategy_ids: list[int] | None = None) -> dict[str, object]:
    service = StrategyService()
    logger.info(
        "Celery task started task=%s task_id=%s strategy_ids=%s",
        self.name,
        self.request.id,
        strategy_ids,
    )
    with SessionLocal() as db:
        runs = service.run_active_strategies(db, strategy_ids=strategy_ids)

    result = {
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
                "items": [item.model_dump() for item in run.items],
            }
            for run in runs
        ],
    }
    logger.info(
        "Celery task succeeded task=%s task_id=%s count=%s",
        self.name,
        self.request.id,
        result["count"],
    )
    return result
