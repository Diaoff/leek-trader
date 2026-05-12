from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class BacktestRunRequest(BaseModel):
    symbol: str
    strategy_id: int | None = None
    strategy_type: Literal["moving_average", "macd", "rl_trading"] = "moving_average"
    start_date: date | None = None
    end_date: date | None = None
    source: str = "baostock"
    adjustflag: str = "2"
    initial_cash: float = Field(default=100000.0, gt=0)
    commission_rate: float = Field(default=0.0003, ge=0)
    slippage_rate: float = Field(default=0.0002, ge=0)
    max_position_pct: float = Field(default=1.0, ge=0, le=1)
    parameters: dict[str, Any] = Field(default_factory=dict)


class BacktestRunRead(BaseModel):
    status: str
    strategy_id: int | None = None
    strategy_name: str | None = None
    strategy_type: str
    symbol: str
    source: str
    adjustflag: str
    bars: int
    initial_cash: float
    final_net_worth: float
    total_return_pct: float
    max_drawdown_pct: float
    trade_count: int
    equity_curve: list[dict[str, Any]] = Field(default_factory=list)
    trades: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class BacktestDailyReviewRequest(BacktestRunRequest):
    pass


class BacktestDailyReviewRead(BaseModel):
    status: str
    review_date: str | None = None
    headline: str
    backtest: BacktestRunRead
    highlights: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class BacktestJobRead(BaseModel):
    job_id: str
    status: str
    progress_step: int = 0
    progress_total: int = 1
    progress_pct: float = 0.0
    progress_label: str = ""
    progress_details: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    result: BacktestRunRead | None = None
    error: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
