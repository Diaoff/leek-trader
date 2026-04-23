from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrategyCreate(BaseModel):
    name: str
    symbol: str
    strategy_type: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class StrategyUpdate(BaseModel):
    name: str | None = None
    symbol: str | None = None
    status: str | None = None
    parameters: dict[str, Any] | None = None


class StrategyRunRead(BaseModel):
    id: int
    strategy_id: int
    status: str
    signal: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StrategyRead(BaseModel):
    id: int
    tenant_id: str
    name: str
    symbol: str
    strategy_type: str
    status: str
    parameters: dict[str, Any]
    latest_signal: str
    signal_symbol: str
    latest_run_status: str | None = None
    latest_run_at: datetime | None = None
    run_count_today: int = 0
    total_run_count: int = 0

    model_config = ConfigDict(from_attributes=True)
