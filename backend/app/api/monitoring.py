import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from kombu.exceptions import OperationalError as KombuOperationalError
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.async_governance import build_task_idempotency_key, get_task_governance
from app.core.audit import audit_event
from app.core.celery_app import celery_app, get_persisted_task_stats, get_task_runtime_stats
from app.core.config import settings
from app.core.auth import get_current_superuser
from app.core.db import get_db
from app.core.logging import logger
from app.models import Account, Order, Position, Trade, User
from app.monitoring.operations import OperationsMetricsService
from app.tasks.market_tasks import refresh_market_quotes_task
from app.tasks.smart_selection_tasks import run_smart_selection_task
from app.tasks.strategy_tasks import run_strategy_cycle_task
from app.tasks.trading_tasks import match_pending_orders_task, monitor_position_guards_task

router = APIRouter()

ASYNC_TASKS: dict[str, dict[str, Any]] = {
    "refresh_market_quotes": {
        "display_name": "行情刷新",
        "task_name": "app.tasks.market_tasks.refresh_market_quotes_task",
        "schedule_name": "refresh-market-quotes",
        "task": refresh_market_quotes_task,
    },
    "run_smart_selection": {
        "display_name": "智能选股",
        "task_name": "app.tasks.smart_selection_tasks.run_smart_selection_task",
        "schedule_name": "run-smart-selection",
        "task": run_smart_selection_task,
    },
    "run_strategy_cycle": {
        "display_name": "策略周期运行",
        "task_name": "app.tasks.strategy_tasks.run_strategy_cycle_task",
        "schedule_name": "run-strategy-cycle",
        "task": run_strategy_cycle_task,
    },
    "match_pending_orders": {
        "display_name": "挂单撮合",
        "task_name": "app.tasks.trading_tasks.match_pending_orders_task",
        "schedule_name": "match-pending-orders",
        "task": match_pending_orders_task,
    },
    "monitor_position_guards": {
        "display_name": "持仓止盈止损巡检",
        "task_name": "app.tasks.trading_tasks.monitor_position_guards_task",
        "schedule_name": "monitor-position-guards",
        "task": monitor_position_guards_task,
    },
}


class RefreshMarketQuotesDispatch(BaseModel):
    symbols: list[str] | None = None


class RunStrategyCycleDispatch(BaseModel):
    strategy_ids: list[int] | None = None


def _is_broker_unavailable_error(error: Exception) -> bool:
    if isinstance(error, (KombuOperationalError, OSError, TimeoutError)):
        return True

    error_type = type(error)
    class_name = error_type.__name__.lower()
    module_name = error_type.__module__.lower()
    message = str(error).lower()
    return (
        class_name in {"operationalerror", "connectionerror", "timeouterror"}
        or "kombu" in module_name
        or "redis" in module_name
        or any(
            marker in message
            for marker in (
                "connection refused",
                "connection is bad",
                "redis",
                "broker",
                "temporarily unavailable",
                "operation not permitted",
            )
        )
    )


def _dispatch_async_task(task_key: str, *, kwargs: dict[str, object] | None = None):
    task = ASYNC_TASKS[task_key]["task"]
    try:
        if kwargs:
            return task.apply_async(kwargs=kwargs)
        return task.apply_async()
    except Exception as error:
        if _is_broker_unavailable_error(error):
            logger.error("Async task dispatch unavailable task=%s error=%s", task_key, error)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="消息队列不可用，请检查 Redis / Celery broker 后重试",
            ) from error
        raise


def _audit_async_dispatch(task_key: str, task_id: str, current_user: User, kwargs: dict[str, object] | None = None) -> None:
    audit_event(
        "async_task.dispatch",
        actor_id=current_user.id,
        actor_name=current_user.username,
        tenant_id=current_user.tenant_id,
        resource_type="async_task",
        resource_id=task_id,
        outcome="queued",
        details={"task": task_key, "kwargs": kwargs or {}, "idempotency_key": build_task_idempotency_key(task_key, kwargs or {})},
    )


def _serialize_retry_policy(task: Any) -> dict[str, object]:
    return {
        "autoretry_for": [exc.__name__ for exc in getattr(task, "autoretry_for", ())],
        "retry_backoff": bool(getattr(task, "retry_backoff", False)),
        "retry_jitter": bool(getattr(task, "retry_jitter", False)),
        "max_retries": getattr(task, "retry_kwargs", {}).get("max_retries"),
    }


def _serialize_schedule(schedule_name: str) -> float | None:
    schedule = celery_app.conf.beat_schedule.get(schedule_name)
    if not schedule:
        return None
    try:
        return float(schedule["schedule"])
    except (TypeError, ValueError):
        return None


def _serialize_schedule_description(schedule_name: str) -> str | None:
    schedule = celery_app.conf.beat_schedule.get(schedule_name)
    if not schedule:
        return None
    schedule_value = schedule["schedule"]
    if hasattr(schedule_value, "_orig_hour") and hasattr(schedule_value, "_orig_minute"):
        return f"{schedule_value._orig_minute} {schedule_value._orig_hour} * * *"
    return None


def _task_summary() -> dict[str, list[dict[str, object]]]:
    persisted_stats = get_persisted_task_stats()
    runtime_stats = get_task_runtime_stats()
    tasks = []
    for task_key, metadata in ASYNC_TASKS.items():
        task_name = metadata["task_name"]
        persisted = persisted_stats.get(task_name, {})
        use_persisted = bool(persisted and persisted.get("started"))
        tasks.append(
            {
                "key": task_key,
                "display_name": metadata["display_name"],
                "task_name": task_name,
                "schedule_seconds": _serialize_schedule(metadata["schedule_name"]),
                "schedule_description": _serialize_schedule_description(metadata["schedule_name"]),
                "retry_policy": _serialize_retry_policy(metadata["task"]),
                "governance": get_task_governance(task_key),
                "idempotency_key_example": build_task_idempotency_key(task_key, {"scheduled": True}),
                "stats_source": "database" if use_persisted else "process",
                "stats": persisted if use_persisted else runtime_stats.get(task_name, {}),
            }
        )
    return {"tasks": tasks}


@router.get("/health")
async def health_check():
    """系统健康检查"""
    start_time = time.time()
    
    # Basic health check
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "Leek Trader Backend",
        "response_time": f"{((time.time() - start_time) * 1000):.2f}ms"
    }
    
    logger.info("Health check performed")
    return health_status


@router.get("/metrics")
async def get_metrics(db: Session = Depends(get_db), current_user: User = Depends(get_current_superuser)):
    """获取系统指标"""
    start_time = time.time()
    
    # Count users
    user_count = db.query(func.count(User.id)).scalar() or 0
    
    # Count accounts
    account_count = db.query(func.count(Account.id)).scalar() or 0
    
    # Count positions
    position_count = db.query(func.count(Position.id)).scalar() or 0
    
    # Count orders
    order_count = db.query(func.count(Order.id)).scalar() or 0
    
    # Count trades
    trade_count = db.query(func.count(Trade.id)).scalar() or 0
    
    # Calculate total equity
    total_equity_result = db.query(func.sum(Account.total_equity)).scalar()
    total_equity = float(total_equity_result) if total_equity_result else 0.0
    
    metrics = {
        "timestamp": datetime.utcnow().isoformat(),
        "users": user_count,
        "accounts": account_count,
        "positions": position_count,
        "orders": order_count,
        "trades": trade_count,
        "total_equity": total_equity,
        "response_time": f"{((time.time() - start_time) * 1000):.2f}ms"
    }
    
    logger.info("Metrics collected")
    return metrics


@router.get("/operations/metrics")
async def get_operations_metrics(
    window_days: int = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """获取核心运行指标。"""
    metrics = OperationsMetricsService(db).build_metrics(window_days=window_days)
    return metrics.to_dict()


@router.get("/async-tasks/summary")
async def get_async_task_summary(current_user: User = Depends(get_current_superuser)):
    """获取异步任务摘要"""
    summary = _task_summary()
    summary["note"] = "任务统计优先读取数据库持久化结果；未落库任务回退为当前 worker 进程内基线数据。"
    summary["panel"] = {
        "ready": True,
        "task_count": len(summary.get("tasks", [])),
        "persisted_stats_enabled": True,
        "log_dir": settings.resolved_log_dir,
    }
    return summary


@router.post("/async-tasks/refresh-market-quotes")
async def dispatch_refresh_market_quotes(payload: RefreshMarketQuotesDispatch, current_user: User = Depends(get_current_superuser)):
    """手动触发行情刷新任务"""
    kwargs = {"symbols": payload.symbols}
    result = _dispatch_async_task("refresh_market_quotes", kwargs=kwargs)
    _audit_async_dispatch("refresh_market_quotes", result.id, current_user, kwargs)
    return {
        "status": "queued",
        "task": "refresh_market_quotes",
        "task_name": ASYNC_TASKS["refresh_market_quotes"]["task_name"],
        "task_id": result.id,
        "symbols": payload.symbols,
    }


@router.post("/async-tasks/run-strategy-cycle")
async def dispatch_run_strategy_cycle(payload: RunStrategyCycleDispatch, current_user: User = Depends(get_current_superuser)):
    """手动触发策略周期任务"""
    kwargs = {"strategy_ids": payload.strategy_ids}
    result = _dispatch_async_task("run_strategy_cycle", kwargs=kwargs)
    _audit_async_dispatch("run_strategy_cycle", result.id, current_user, kwargs)
    return {
        "status": "queued",
        "task": "run_strategy_cycle",
        "task_name": ASYNC_TASKS["run_strategy_cycle"]["task_name"],
        "task_id": result.id,
        "strategy_ids": payload.strategy_ids,
    }


@router.post("/async-tasks/match-pending-orders")
async def dispatch_match_pending_orders(current_user: User = Depends(get_current_superuser)):
    """手动触发挂单撮合任务"""
    result = _dispatch_async_task("match_pending_orders")
    _audit_async_dispatch("match_pending_orders", result.id, current_user)
    return {
        "status": "queued",
        "task": "match_pending_orders",
        "task_name": ASYNC_TASKS["match_pending_orders"]["task_name"],
        "task_id": result.id,
    }


@router.post("/async-tasks/monitor-position-guards")
async def dispatch_monitor_position_guards(current_user: User = Depends(get_current_superuser)):
    """手动触发持仓止盈止损巡检任务"""
    result = _dispatch_async_task("monitor_position_guards")
    _audit_async_dispatch("monitor_position_guards", result.id, current_user)
    return {
        "status": "queued",
        "task": "monitor_position_guards",
        "task_name": ASYNC_TASKS["monitor_position_guards"]["task_name"],
        "task_id": result.id,
    }


@router.get("/logs/latest")
async def get_latest_logs(limit: int = 50, current_user: User = Depends(get_current_superuser)):
    """获取最新日志"""
    try:
        log_file = f"{settings.resolved_log_dir}/app.log"
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        latest_logs = lines[-limit:] if len(lines) > limit else lines
        
        return {
            "logs": latest_logs,
            "count": len(latest_logs),
            "total": len(lines)
        }
    except Exception as e:
        logger.error(f"Error reading logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read logs"
        )


@router.get("/system/stats")
async def get_system_stats(current_user: User = Depends(get_current_superuser)):
    """获取系统统计信息"""
    import psutil
    import os
    
    try:
        # Get system stats
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        stats = {
            "cpu_percent": cpu_percent,
            "memory": {
                "total": memory.total,
                "available": memory.available,
                "used": memory.used,
                "percent": memory.percent
            },
            "disk": {
                "total": disk.total,
                "used": disk.used,
                "free": disk.free,
                "percent": disk.percent
            },
            "pid": os.getpid(),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return stats
    except ImportError:
        return {
            "message": "psutil not installed, system stats not available",
            "timestamp": datetime.utcnow().isoformat()
        }
