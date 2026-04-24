import logging
from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock

from celery import Celery, Task

from app.core.config import settings

logger = logging.getLogger(__name__)

broker_url = settings.celery_broker_url or settings.redis_url
result_backend = settings.celery_result_backend or settings.redis_url
KNOWN_TASK_NAMES = (
    "app.tasks.market_tasks.refresh_market_quotes_task",
    "app.tasks.strategy_tasks.run_strategy_cycle_task",
    "app.tasks.trading_tasks.match_pending_orders_task",
)
_task_runtime_stats_lock = Lock()
_task_runtime_stats: dict[str, dict[str, object]] = {}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_runtime_stats(task_name: str) -> dict[str, object]:
    return {
        "task_name": task_name,
        "started": 0,
        "succeeded": 0,
        "failed": 0,
        "retried": 0,
        "last_task_id": None,
        "last_started_at": None,
        "last_succeeded_at": None,
        "last_failed_at": None,
        "last_retried_at": None,
        "last_error": None,
        "last_retry_error": None,
    }


def _update_runtime_stats(
    task_name: str,
    event: str,
    *,
    task_id: str | None = None,
    error: Exception | None = None,
) -> None:
    with _task_runtime_stats_lock:
        stats = _task_runtime_stats.setdefault(task_name, _default_runtime_stats(task_name))
        stats["last_task_id"] = task_id
        if event == "started":
            stats["started"] = int(stats["started"]) + 1
            stats["last_started_at"] = _timestamp()
        elif event == "succeeded":
            stats["succeeded"] = int(stats["succeeded"]) + 1
            stats["last_succeeded_at"] = _timestamp()
        elif event == "failed":
            stats["failed"] = int(stats["failed"]) + 1
            stats["last_failed_at"] = _timestamp()
            stats["last_error"] = str(error) if error else None
        elif event == "retried":
            stats["retried"] = int(stats["retried"]) + 1
            stats["last_retried_at"] = _timestamp()
            stats["last_retry_error"] = str(error) if error else None


def get_task_runtime_stats() -> dict[str, dict[str, object]]:
    with _task_runtime_stats_lock:
        for task_name in KNOWN_TASK_NAMES:
            _task_runtime_stats.setdefault(task_name, _default_runtime_stats(task_name))
        return deepcopy(_task_runtime_stats)


class ReliableTask(Task):
    autoretry_for = (Exception,)
    retry_backoff = True
    retry_jitter = True
    retry_kwargs = {"max_retries": 3}

    def before_start(self, task_id, args, kwargs) -> None:  # type: ignore[override]
        _update_runtime_stats(self.name, "started", task_id=task_id)

    def on_retry(self, exc, task_id, args, kwargs, einfo) -> None:  # type: ignore[override]
        _update_runtime_stats(self.name, "retried", task_id=task_id, error=exc)
        logger.warning(
            "Celery task retry scheduled task=%s task_id=%s retries=%s error=%s",
            self.name,
            task_id,
            self.request.retries,
            exc,
        )

    def on_success(self, retval, task_id, args, kwargs) -> None:  # type: ignore[override]
        _update_runtime_stats(self.name, "succeeded", task_id=task_id)

    def on_failure(self, exc, task_id, args, kwargs, einfo) -> None:  # type: ignore[override]
        _update_runtime_stats(self.name, "failed", task_id=task_id, error=exc)
        logger.error(
            "Celery task failed task=%s task_id=%s retries=%s error=%s",
            self.name,
            task_id,
            self.request.retries,
            exc,
        )


celery_app = Celery(
    "leek_trader",
    broker=broker_url,
    backend=result_backend,
    include=["app.tasks.market_tasks", "app.tasks.trading_tasks", "app.tasks.strategy_tasks"],
    task_cls=ReliableTask,
)

celery_app.conf.imports = ("app.tasks.market_tasks", "app.tasks.trading_tasks", "app.tasks.strategy_tasks")
celery_app.conf.task_track_started = True
celery_app.conf.task_send_sent_event = True
celery_app.conf.beat_schedule = {
    "refresh-market-quotes": {
        "task": "app.tasks.market_tasks.refresh_market_quotes_task",
        "schedule": float(settings.market_refresh_interval_seconds),
    },
    "run-strategy-cycle": {
        "task": "app.tasks.strategy_tasks.run_strategy_cycle_task",
        "schedule": 60.0,
    },
    "match-pending-orders": {
        "task": "app.tasks.trading_tasks.match_pending_orders_task",
        "schedule": 5.0,
    }
}
celery_app.conf.timezone = "Asia/Shanghai"
