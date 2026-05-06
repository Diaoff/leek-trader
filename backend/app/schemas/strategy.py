from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrategyCreate(BaseModel):
    name: str
    symbol: str | None = None
    target_type: str | None = None
    target_config: dict[str, Any] | None = None
    strategy_type: str
    execution_mode: str = "signal_only"
    parameters: dict[str, Any] = Field(default_factory=dict)


class StrategyUpdate(BaseModel):
    name: str | None = None
    symbol: str | None = None
    target_type: str | None = None
    target_config: dict[str, Any] | None = None
    strategy_type: str | None = None
    status: str | None = None
    execution_mode: str | None = None
    parameters: dict[str, Any] | None = None


class StrategyRunItemRead(BaseModel):
    id: int
    symbol: str
    name: str | None = None
    signal: dict[str, Any]
    order_submitted: bool = False
    order_id: int | None = None
    order_status: str | None = None
    side: str | None = None
    quantity: int | None = None
    price: float | None = None
    reason: str | None = None
    strength: str | None = None
    trigger_reason: str | None = None
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    position_pct: float | None = None
    recommendation_confirmed: bool | None = None
    confirmation_source: str | None = None
    recommendation_snapshot_date: str | None = None
    position_add_path: str | None = None
    execution_blockers: list[str] = Field(default_factory=list)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StrategyRunRead(BaseModel):
    id: int
    strategy_id: int
    status: str
    signal: dict[str, Any]
    execution_mode: str | None = None
    order_submitted: bool = False
    order_id: int | None = None
    order_status: str | None = None
    side: str | None = None
    quantity: int | None = None
    price: float | None = None
    reason: str | None = None
    strength: str | None = None
    trigger_reason: str | None = None
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    position_pct: float | None = None
    recommendation_confirmed: bool | None = None
    confirmation_source: str | None = None
    recommendation_snapshot_date: str | None = None
    position_add_path: str | None = None
    execution_blockers: list[str] = Field(default_factory=list)
    items: list[StrategyRunItemRead] = Field(default_factory=list)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StrategyRunHistoryRead(BaseModel):
    runs: list[StrategyRunRead] = Field(default_factory=list)


class StrategyDeleteRead(BaseModel):
    status: str
    id: int


class StrategyRead(BaseModel):
    id: int
    tenant_id: str
    name: str
    symbol: str
    target_type: str
    target_config: dict[str, Any]
    strategy_type: str
    status: str
    execution_mode: str
    parameters: dict[str, Any]
    latest_signal: str
    latest_signal_summary: str | None = None
    signal_symbol: str
    signal_symbol_display: str | None = None
    resolved_target_count: int = 0
    latest_run_status: str | None = None
    latest_run_at: datetime | None = None
    run_count_today: int = 0
    total_run_count: int = 0

    model_config = ConfigDict(from_attributes=True)
