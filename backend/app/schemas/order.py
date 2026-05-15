from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrderCreate(BaseModel):
    symbol: str
    side: Literal['buy', 'sell']
    order_type: Literal['market', 'limit']
    quantity: int = Field(gt=0)
    price: Decimal = Field(gt=0)
    stop_loss_price: Decimal | None = Field(default=None, gt=0)
    take_profit_price: Decimal | None = Field(default=None, gt=0)


class OrderRead(BaseModel):
    id: int
    tenant_id: str
    account_id: int
    symbol: str
    name: str | None = None
    side: Literal['buy', 'sell']
    order_type: Literal['market', 'limit']
    status: Literal['pending', 'accepted', 'filled', 'rejected', 'cancelled', 'expired']
    quantity: int
    price: Decimal
    filled_quantity: int
    filled_price: Decimal
    reject_reason: str | None
    risk_rule_version: str | None = None
    correlation_id: str | None = None
    strategy_id: int | None = None
    strategy_run_id: int | None = None

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    @field_validator("side", "order_type", "status", mode="before")
    @classmethod
    def _coerce_enum_values(cls, value):
        return getattr(value, "value", value)
