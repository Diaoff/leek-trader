import logging
from datetime import datetime, timedelta, timezone

from app.core.celery_app import celery_app
from app.core.db import SessionLocal
from app.core.trading_calendar import is_trading_time
from app.preferences.service import PreferenceService
from app.strategy.service import StrategyService

logger = logging.getLogger(__name__)
_last_scheduled_run_at: datetime | None = None


@celery_app.task(name="app.tasks.strategy_tasks.run_strategy_cycle_task", bind=True)
def run_strategy_cycle_task(self, strategy_ids: list[int] | None = None, scheduled: bool = False) -> dict[str, object]:
    global _last_scheduled_run_at

    with SessionLocal() as db:
        if scheduled:
            preferences = PreferenceService().strategy_scheduler_preferences(db=db)
            if not preferences.enabled:
                return _skip_result("scheduler_disabled", strategy_ids)
            if preferences.trading_hours_only and not is_trading_time():
                return _skip_result("outside_trading_hours", strategy_ids)
            now = datetime.now(timezone.utc)
            if _last_scheduled_run_at is not None:
                elapsed = now - _last_scheduled_run_at
                if elapsed < timedelta(seconds=preferences.interval_seconds):
                    return _skip_result("interval_not_due", strategy_ids, next_due_seconds=int((timedelta(seconds=preferences.interval_seconds) - elapsed).total_seconds()))

        service = StrategyService()
        logger.info(
            "Celery task started task=%s task_id=%s strategy_ids=%s",
            self.name,
            self.request.id,
            strategy_ids,
        )
        runs = service.run_active_strategies(db, strategy_ids=strategy_ids)
        if scheduled:
            _last_scheduled_run_at = datetime.now(timezone.utc)

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


def _skip_result(reason: str, strategy_ids: list[int] | None, **extra: object) -> dict[str, object]:
    return {
        "status": "skipped",
        "task": "run_strategy_cycle",
        "reason": reason,
        "scheduled": True,
        "strategy_ids": strategy_ids or [],
        **extra,
    }
