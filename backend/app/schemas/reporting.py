from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ReportingSummary(BaseModel):
    trade_count: int
    realized_pnl: float
    win_rate: float
    cumulative_return: float
    profit_factor: float
    max_drawdown: float
    avg_win: float
    avg_loss: float
    annualized_return_pct: float | None = None
    annualized_volatility_pct: float | None = None
    sharpe_ratio: float | None = None
    calmar_ratio: float | None = None


class EquityCurvePoint(BaseModel):
    label: str
    total_equity: float


class PeriodStat(BaseModel):
    period: str
    trade_count: int
    realized_pnl: float
    ending_equity: float


class EventLogRead(BaseModel):
    id: int
    tenant_id: str
    user_id: int | None = None
    account_id: int | None = None
    event_type: str
    symbol: str | None = None
    occurred_at: datetime
    strategy_id: int | None = None
    strategy_run_id: int | None = None
    order_id: int | None = None
    order_event_id: int | None = None
    trade_id: int | None = None
    position_id: int | None = None
    equity_snapshot_id: int | None = None
    correlation_id: str | None = None
    risk_rule_version: str | None = None
    payload: dict[str, Any]
