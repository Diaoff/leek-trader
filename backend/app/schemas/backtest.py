from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class BacktestRunRequest(BaseModel):
    symbol: str
    strategy_id: int | None = None
    strategy_type: Literal["moving_average", "macd", "rl_trading", "rsi_reversal", "bollinger_band", "kdj_momentum", "signal_fusion"] = "moving_average"
    start_date: date | None = None
    end_date: date | None = None
    source: str = "baostock"
    adjustflag: str = "2"
    initial_cash: float = Field(default=100000.0, gt=0)
    commission_rate: float = Field(default=0.0003, ge=0)
    slippage_rate: float = Field(default=0.0002, ge=0)
    max_position_pct: float = Field(default=1.0, ge=0, le=1)
    parameters: dict[str, Any] = Field(default_factory=dict)


class PortfolioBacktestRequest(BaseModel):
    symbols: list[str] = Field(min_length=1)
    weights: list[float] | None = None
    strategy_id: int | None = None
    strategy_type: Literal["moving_average", "macd", "rl_trading", "rsi_reversal", "bollinger_band", "kdj_momentum", "signal_fusion"] = "moving_average"
    start_date: date | None = None
    end_date: date | None = None
    source: str = "baostock"
    adjustflag: str = "2"
    initial_cash: float = Field(default=100000.0, gt=0)
    commission_rate: float = Field(default=0.0003, ge=0)
    slippage_rate: float = Field(default=0.0002, ge=0)
    max_position_pct: float = Field(default=1.0, ge=0, le=1)
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_weights(self) -> "PortfolioBacktestRequest":
        self.symbols = [symbol.strip() for symbol in self.symbols if symbol.strip()]
        if not self.symbols:
            raise ValueError("symbols must not be empty")
        if self.weights is not None:
            if len(self.weights) != len(self.symbols):
                raise ValueError("weights length must match symbols")
            if any(weight <= 0 for weight in self.weights):
                raise ValueError("weights must be positive")
            if sum(self.weights) <= 0:
                raise ValueError("weights sum must be positive")
        return self


class BacktestOptimizationRequest(BaseModel):
    symbol: str
    strategy_id: int | None = None
    strategy_type: Literal["moving_average", "macd", "rl_trading", "rsi_reversal", "bollinger_band", "kdj_momentum", "signal_fusion"] = "moving_average"
    start_date: date | None = None
    end_date: date | None = None
    source: str = "baostock"
    adjustflag: str = "2"
    initial_cash: float = Field(default=100000.0, gt=0)
    commission_rate: float = Field(default=0.0003, ge=0)
    slippage_rate: float = Field(default=0.0002, ge=0)
    max_position_pct: float = Field(default=1.0, ge=0, le=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    parameter_grid: dict[str, list[Any]] = Field(default_factory=dict)
    target_metric: Literal["total_return_pct", "max_drawdown_pct", "sharpe_ratio", "final_net_worth"] = "total_return_pct"
    sort_direction: Literal["asc", "desc"] = "desc"
    out_of_sample: dict[str, date | None] | None = None

    @model_validator(mode="after")
    def validate_grid(self) -> "BacktestOptimizationRequest":
        if not self.parameter_grid:
            raise ValueError("parameter_grid must not be empty")
        combinations = 1
        for key, values in self.parameter_grid.items():
            if not key.strip():
                raise ValueError("parameter_grid keys must not be empty")
            if not values:
                raise ValueError("parameter_grid values must not be empty")
            combinations *= len(values)
        if combinations > 30:
            raise ValueError("parameter_grid combinations must be <= 30")
        if self.out_of_sample is not None:
            start_date = self.out_of_sample.get("start_date")
            end_date = self.out_of_sample.get("end_date")
            if start_date is None or end_date is None:
                raise ValueError("out_of_sample requires start_date and end_date")
            if start_date > end_date:
                raise ValueError("out_of_sample start_date must be <= end_date")
        return self


class PortfolioBacktestRead(BaseModel):
    status: str
    strategy_id: int | None = None
    strategy_name: str | None = None
    strategy_type: str
    symbols: list[str] = Field(default_factory=list)
    weights: list[float] = Field(default_factory=list)
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


class BacktestOptimizationRead(BaseModel):
    status: str
    strategy_id: int | None = None
    strategy_name: str | None = None
    strategy_type: str
    symbol: str
    source: str
    adjustflag: str
    target_metric: str
    sort_direction: str
    bars: int
    parameter_grid: dict[str, list[Any]] = Field(default_factory=dict)
    combinations: int
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    matrix: list[dict[str, Any]] = Field(default_factory=list)
    best_candidate: dict[str, Any] | None = None
    out_of_sample: dict[str, Any] | None = None
    summary: dict[str, Any] = Field(default_factory=dict)


class BacktestOptimizationJobRead(BaseModel):
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
    result: dict[str, Any] | BacktestOptimizationRead | None = None
    error: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class BacktestOptimizationHistoryRead(BaseModel):
    job_id: str
    created_at: str | None = None
    updated_at: str | None = None
    symbol: str
    strategy_type: str
    strategy_id: int | None = None
    strategy_name: str | None = None
    target_metric: str
    best_parameters: dict[str, Any] = Field(default_factory=dict)
    best_result: dict[str, Any] = Field(default_factory=dict)
    out_of_sample: dict[str, Any] | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


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
    result: dict[str, Any] | BacktestRunRead | PortfolioBacktestRead | None = None
    error: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
