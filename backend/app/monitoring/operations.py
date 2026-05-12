from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.market_daily_bar import MarketDailyBar
from app.models.order import Order, OrderStatus
from app.models.strategy_run import StrategyRun, StrategyRunStatus
from app.models.trade import Trade


@dataclass(slots=True)
class OperationsMetrics:
    status: str
    generated_at: str
    window_days: int
    market_data: dict[str, Any]
    strategy_execution: dict[str, Any]
    trading: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "generated_at": self.generated_at,
            "window_days": self.window_days,
            "market_data": self.market_data,
            "strategy_execution": self.strategy_execution,
            "trading": self.trading,
        }


class OperationsMetricsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def build_metrics(self, *, window_days: int = 7, reference_date: date | None = None) -> OperationsMetrics:
        safe_window_days = max(1, min(window_days, 365))
        reference = reference_date or date.today()
        return OperationsMetrics(
            status="ready",
            generated_at=datetime.utcnow().isoformat(),
            window_days=safe_window_days,
            market_data=self._market_data_metrics(reference),
            strategy_execution=self._strategy_metrics(safe_window_days),
            trading=self._trading_metrics(safe_window_days),
        )

    def _market_data_metrics(self, reference_date: date) -> dict[str, Any]:
        latest_date = self.db.scalar(select(func.max(MarketDailyBar.trade_date)))
        row_count = int(self.db.scalar(select(func.count(MarketDailyBar.id))) or 0)
        symbol_count = int(self.db.scalar(select(func.count(func.distinct(MarketDailyBar.symbol)))) or 0)
        source_count = int(self.db.scalar(select(func.count(func.distinct(MarketDailyBar.source)))) or 0)
        staleness_days = max((reference_date - latest_date).days, 0) if latest_date else None
        status = "empty" if latest_date is None else "stale" if staleness_days is not None and staleness_days > 5 else "fresh"
        return {
            "status": status,
            "latest_trade_date": latest_date.isoformat() if latest_date else None,
            "staleness_days": staleness_days,
            "daily_bar_rows": row_count,
            "symbol_count": symbol_count,
            "source_count": source_count,
        }

    def _strategy_metrics(self, window_days: int) -> dict[str, Any]:
        total = int(self.db.scalar(select(func.count(StrategyRun.id))) or 0)
        succeeded = int(self.db.scalar(select(func.count(StrategyRun.id)).where(StrategyRun.status == StrategyRunStatus.SUCCESS)) or 0)
        failed = int(self.db.scalar(select(func.count(StrategyRun.id)).where(StrategyRun.status == StrategyRunStatus.FAILED)) or 0)
        success_rate = round(succeeded / total, 4) if total else None
        latest_run_at = self.db.scalar(select(func.max(StrategyRun.created_at)))
        return {
            "window_days": window_days,
            "total_runs": total,
            "succeeded_runs": succeeded,
            "failed_runs": failed,
            "success_rate": success_rate,
            "latest_run_at": latest_run_at.isoformat() if latest_run_at else None,
        }

    def _trading_metrics(self, window_days: int) -> dict[str, Any]:
        total_orders = int(self.db.scalar(select(func.count(Order.id))) or 0)
        filled_orders = int(self.db.scalar(select(func.count(Order.id)).where(Order.status == OrderStatus.FILLED)) or 0)
        rejected_orders = int(self.db.scalar(select(func.count(Order.id)).where(Order.status == OrderStatus.REJECTED)) or 0)
        cancelled_orders = int(self.db.scalar(select(func.count(Order.id)).where(Order.status == OrderStatus.CANCELLED)) or 0)
        pending_orders = int(self.db.scalar(select(func.count(Order.id)).where(Order.status == OrderStatus.PENDING)) or 0)
        trade_count = int(self.db.scalar(select(func.count(Trade.id))) or 0)
        success_rate = round(filled_orders / total_orders, 4) if total_orders else None
        latest_order_at = self.db.scalar(select(func.max(Order.created_at)))
        latest_trade_at = self.db.scalar(select(func.max(Trade.executed_at)))
        return {
            "window_days": window_days,
            "total_orders": total_orders,
            "filled_orders": filled_orders,
            "rejected_orders": rejected_orders,
            "cancelled_orders": cancelled_orders,
            "pending_orders": pending_orders,
            "trade_count": trade_count,
            "order_success_rate": success_rate,
            "latest_order_at": latest_order_at.isoformat() if latest_order_at else None,
            "latest_trade_at": latest_trade_at.isoformat() if latest_trade_at else None,
        }
