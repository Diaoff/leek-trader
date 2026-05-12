from decimal import Decimal

from pydantic import BaseModel, Field


class TradingStateResetRequest(BaseModel):
    confirmation: str = Field(description="Must be RESET")
    initial_cash: Decimal | None = Field(default=None, ge=0)


class TradingStateResetRead(BaseModel):
    account_id: int
    tenant_id: str
    account_name: str
    initial_cash: Decimal
    available_cash: Decimal
    total_equity: Decimal
    deleted_counts: dict[str, int]


class SystemBenchmarkRead(BaseModel):
    status: str
    generated_at: str
    samples: dict[str, dict[str, float | int | str]]
    summary: dict[str, float | int | str]
