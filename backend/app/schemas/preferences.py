from typing import Any, Literal

from pydantic import BaseModel, Field


class TradingPreferences(BaseModel):
    commission_rate: float = Field(default=0.0003, ge=0, le=0.1)
    min_commission: float = Field(default=5.0, ge=0)
    stamp_tax_rate: float = Field(default=0.0005, ge=0, le=0.1)
    stamp_tax_side: Literal["sell"] = "sell"


class StrategySchedulerPreferences(BaseModel):
    enabled: bool = True
    interval_seconds: int = Field(default=300, ge=60, le=86400)
    trading_hours_only: bool = True


class SmartSelectionPreferences(BaseModel):
    enabled: bool = True
    schedule_time: str = "20:00"
    config_payload: dict[str, Any] = Field(default_factory=dict)


class PreferencesRead(BaseModel):
    tenant_id: str
    trading: TradingPreferences
    smart_selection: SmartSelectionPreferences
    strategy_scheduler: StrategySchedulerPreferences
    updated_at: str


class TradingPreferencesUpdate(BaseModel):
    commission_rate: float | None = Field(default=None, ge=0, le=0.1)
    min_commission: float | None = Field(default=None, ge=0)
    stamp_tax_rate: float | None = Field(default=None, ge=0, le=0.1)


class StrategySchedulerPreferencesUpdate(BaseModel):
    enabled: bool | None = None
    interval_seconds: int | None = Field(default=None, ge=60, le=86400)
    trading_hours_only: bool | None = None


class SmartSelectionPreferencesUpdate(BaseModel):
    enabled: bool | None = None
    config_payload: dict[str, Any] | None = None


class PreferencesUpdate(BaseModel):
    trading: TradingPreferencesUpdate | None = None
    smart_selection: SmartSelectionPreferencesUpdate | None = None
    strategy_scheduler: StrategySchedulerPreferencesUpdate | None = None
