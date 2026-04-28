import logging

from app.core.celery_app import celery_app
from app.core.db import SessionLocal
from app.trading.service import TradingService

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.trading_tasks.match_pending_orders_task", bind=True)
def match_pending_orders_task(self) -> dict[str, object]:
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
def monitor_position_guards_task(self) -> dict[str, object]:
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
