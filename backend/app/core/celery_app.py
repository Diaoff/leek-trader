import logging
from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock

from celery import Celery, Task
from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal, engine
from app.models.async_task_execution import AsyncTaskExecution, AsyncTaskExecutionStatus

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
_persistence_schema_lock = Lock()
_persistence_schema_ready = False


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


def _ensure_persistence_schema() -> None:
    global _persistence_schema_ready

    if _persistence_schema_ready:
        return

    with _persistence_schema_lock:
        if _persistence_schema_ready:
            return
        AsyncTaskExecution.__table__.create(bind=engine, checkfirst=True)
        _persistence_schema_ready = True


def _persist_task_event(
    task_name: str,
    event: str,
    *,
    task_id: str | None = None,
    error: Exception | None = None,
) -> None:
    if not task_id:
        return

    try:
        _ensure_persistence_schema()
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            execution = db.scalar(select(AsyncTaskExecution).where(AsyncTaskExecution.task_id == task_id))
            if execution is None:
                execution = AsyncTaskExecution(
                    task_id=task_id,
                    task_name=task_name,
                    started_at=now,
                    last_event_at=now,
                )

            execution.task_name = task_name
            execution.last_event_at = now
            if execution.started_at is None:
                execution.started_at = now

            if event == "started":
                execution.status = AsyncTaskExecutionStatus.STARTED
            elif event == "retried":
                execution.status = AsyncTaskExecutionStatus.RETRYING
                execution.retry_count += 1
                execution.last_retried_at = now
                execution.last_retry_error = str(error) if error else None
            elif event == "succeeded":
                execution.status = AsyncTaskExecutionStatus.SUCCEEDED
                execution.finished_at = now
            elif event == "failed":
                execution.status = AsyncTaskExecutionStatus.FAILED
                execution.finished_at = now
                execution.last_error = str(error) if error else None

            db.add(execution)
            db.commit()
    except Exception as persistence_error:
        logger.warning(
            "Async task persistence failed task=%s task_id=%s event=%s error=%s",
            task_name,
            task_id,
            event,
            persistence_error,
        )


def _emit_async_task_alert(task_name: str, task_id: str | None, error: Exception) -> None:
    logger.error(
        "ASYNC_TASK_ALERT task=%s task_id=%s error=%s",
        task_name,
        task_id,
        error,
    )


def get_task_runtime_stats() -> dict[str, dict[str, object]]:
    with _task_runtime_stats_lock:
        for task_name in KNOWN_TASK_NAMES:
            _task_runtime_stats.setdefault(task_name, _default_runtime_stats(task_name))
        return deepcopy(_task_runtime_stats)


def _latest_datetime_value(rows: list[AsyncTaskExecution], attribute: str) -> str | None:
    values = [value.isoformat() for row in rows if (value := getattr(row, attribute)) is not None]
    return max(values) if values else None


def get_persisted_task_stats() -> dict[str, dict[str, object]]:
    try:
        _ensure_persistence_schema()
        with SessionLocal() as db:
            rows = db.scalars(
                select(AsyncTaskExecution)
                .where(AsyncTaskExecution.task_name.in_(KNOWN_TASK_NAMES))
                .order_by(AsyncTaskExecution.last_event_at.desc())
            ).all()
    except Exception as error:
        logger.warning("Async task stats query failed error=%s", error)
        rows = []

    result = {task_name: _default_runtime_stats(task_name) for task_name in KNOWN_TASK_NAMES}
    grouped_rows: dict[str, list[AsyncTaskExecution]] = {task_name: [] for task_name in KNOWN_TASK_NAMES}
    for row in rows:
        grouped_rows.setdefault(row.task_name, []).append(row)

    for task_name, task_rows in grouped_rows.items():
        if not task_rows:
            continue

        latest = task_rows[0]
        latest_failed = next((row for row in task_rows if row.last_error), None)
        latest_retried = next((row for row in task_rows if row.last_retry_error), None)
        result[task_name] = {
            "task_name": task_name,
            "started": len(task_rows),
            "succeeded": sum(row.status == AsyncTaskExecutionStatus.SUCCEEDED for row in task_rows),
            "failed": sum(row.status == AsyncTaskExecutionStatus.FAILED for row in task_rows),
            "retried": sum(row.retry_count for row in task_rows),
            "last_task_id": latest.task_id,
            "last_started_at": _latest_datetime_value(task_rows, "started_at"),
            "last_succeeded_at": _latest_datetime_value(
                [row for row in task_rows if row.status == AsyncTaskExecutionStatus.SUCCEEDED],
                "finished_at",
            ),
            "last_failed_at": _latest_datetime_value(
                [row for row in task_rows if row.status == AsyncTaskExecutionStatus.FAILED],
                "finished_at",
            ),
            "last_retried_at": _latest_datetime_value(
                [row for row in task_rows if row.last_retried_at is not None],
                "last_retried_at",
            ),
            "last_error": latest_failed.last_error if latest_failed else None,
            "last_retry_error": latest_retried.last_retry_error if latest_retried else None,
        }

    return result


class ReliableTask(Task):
    autoretry_for = (Exception,)
    retry_backoff = True
    retry_jitter = True
    retry_kwargs = {"max_retries": 3}

    def before_start(self, task_id, args, kwargs) -> None:  # type: ignore[override]
        _update_runtime_stats(self.name, "started", task_id=task_id)
        _persist_task_event(self.name, "started", task_id=task_id)

    def on_retry(self, exc, task_id, args, kwargs, einfo) -> None:  # type: ignore[override]
        _update_runtime_stats(self.name, "retried", task_id=task_id, error=exc)
        _persist_task_event(self.name, "retried", task_id=task_id, error=exc)
        logger.warning(
            "Celery task retry scheduled task=%s task_id=%s retries=%s error=%s",
            self.name,
            task_id,
            self.request.retries,
            exc,
        )

    def on_success(self, retval, task_id, args, kwargs) -> None:  # type: ignore[override]
        _update_runtime_stats(self.name, "succeeded", task_id=task_id)
        _persist_task_event(self.name, "succeeded", task_id=task_id)

    def on_failure(self, exc, task_id, args, kwargs, einfo) -> None:  # type: ignore[override]
        _update_runtime_stats(self.name, "failed", task_id=task_id, error=exc)
        _persist_task_event(self.name, "failed", task_id=task_id, error=exc)
        _emit_async_task_alert(self.name, task_id, exc)
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
