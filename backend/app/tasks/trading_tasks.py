from app.core.celery_app import celery_app
from app.core.db import SessionLocal
from app.trading.service import TradingService


@celery_app.task(name="app.tasks.trading_tasks.match_pending_orders_task")
def match_pending_orders_task() -> dict[str, object]:
    service = TradingService()
    with SessionLocal() as db:
        return service.match_pending_orders(db)
