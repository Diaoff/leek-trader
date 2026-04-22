from celery import Celery

from app.core.config import settings

broker_url = settings.celery_broker_url or settings.redis_url
result_backend = settings.celery_result_backend or settings.redis_url

celery_app = Celery(
    "leek_trader",
    broker=broker_url,
    backend=result_backend,
    include=["app.tasks.trading_tasks"],
)

celery_app.conf.imports = ("app.tasks.trading_tasks",)
celery_app.conf.beat_schedule = {
    "match-pending-orders": {
        "task": "app.tasks.trading_tasks.match_pending_orders_task",
        "schedule": 5.0,
    }
}
celery_app.conf.timezone = "Asia/Shanghai"
