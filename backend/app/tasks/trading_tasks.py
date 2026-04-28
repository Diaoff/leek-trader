import logging

from app.core.celery_app import celery_app
from app.core.db import SessionLocal
from app.core.trading_calendar import is_trading_time
from app.trading.service import TradingService

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.trading_tasks.match_pending_orders_task", bind=True)
def match_pending_orders_task(self, scheduled: bool = False) -> dict[str, object]:
    if scheduled and not is_trading_time():
        logger.info(
            "Celery task skipped task=%s task_id=%s reason=outside_trading_hours",
            self.name,
            self.request.id,
        )
        return _outside_trading_hours_result("match_pending_orders")

    service = TradingService()
    logger.info(
        "Celery task started task=%s task_id=%s",
        self.name,
        self.request.id,
    )
    with SessionLocal() as db:
        result = service.match_pending_orders(db)
    logger.info(
        "Celery task succeeded task=%s task_id=%s matched_count=%s",
        self.name,
        self.request.id,
        result.get("matched_count"),
    )
    return result


@celery_app.task(name="app.tasks.trading_tasks.monitor_position_guards_task", bind=True)
def monitor_position_guards_task(self, scheduled: bool = False) -> dict[str, object]:
    if scheduled and not is_trading_time():
        logger.info(
            "Celery task skipped task=%s task_id=%s reason=outside_trading_hours",
            self.name,
            self.request.id,
        )
        return _outside_trading_hours_result("monitor_position_guards")

    service = TradingService()
    logger.info(
        "Celery task started task=%s task_id=%s",
        self.name,
        self.request.id,
    )
    with SessionLocal() as db:
        result = service.monitor_position_guards(db)
    logger.info(
        "Celery task succeeded task=%s task_id=%s triggered_count=%s",
        self.name,
        self.request.id,
        result.get("triggered_count"),
    )
    return result


def _outside_trading_hours_result(task: str) -> dict[str, object]:
    return {
        "status": "skipped",
        "task": task,
        "reason": "outside_trading_hours",
        "scheduled": True,
    }
